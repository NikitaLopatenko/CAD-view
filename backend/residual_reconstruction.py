"""
Execution-guided residual refinement for clean multi-feature CAD.

CADENA's central practical insight is that the next operation should be chosen
from geometry left unexplained by the current build. This module implements a
deterministic version for the operations CAD-View can already export reliably:
localized axial bosses and cuts. Every proposed operation is executed with the
boolean kernel and retained only when geometric agreement improves enough to
pay a feature-count penalty.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon

from parametric_reconstruction import (
    LengthUnit,
    ParametricReconstructionError,
    _circle_fit,
    _coordinates,
)
from revolve_reconstruction import (
    fit_axisymmetric_residual,
    revolve_profile_solid,
)
from solid_agreement import (
    AgreementReport,
    as_volume,
    boolean_backend_available,
    canonical_mesh,
    evaluate_candidate,
)
from surface_analysis import analyze_surface_patches

MAX_REFINEMENT_STEPS = 4
DEFAULT_BEAM_WIDTH = 3
MIN_SELECTION_IMPROVEMENT = 0.008
FEATURE_COMPLEXITY_PENALTY = 0.003
SATISFIED_VOLUME_IOU = 0.98
MAX_COMPONENTS_PER_KIND = 5
MIN_COMPONENT_VOLUME_FRACTION = 0.0005
OFF_AXIS_COMPLEXITY_PENALTY = 0.0005
RADIAL_AXIS_ALIGNMENT = 0.98


@dataclass
class _RefinementState:
    solid: trimesh.Trimesh
    report: AgreementReport
    added_features: tuple[dict[str, Any], ...]
    accepted_ids: frozenset[str]
    objective: float
    ranking_objective: float
    state_id: str


def _loop_coordinates(loop: dict[str, Any]) -> list[list[float]]:
    if loop.get("kind") == "circle":
        center = loop["center"]
        radius = float(loop["radius"])
        ring = Point(float(center[0]), float(center[1])).buffer(
            radius, resolution=64
        )
        return _coordinates(ring.exterior.coords)
    return [
        [float(point[0]), float(point[1])]
        for point in loop.get("points", [])
    ]


def sketch_polygon(sketch: dict[str, Any]) -> Polygon:
    """Convert a serialized CAD-View sketch to a valid Shapely polygon."""
    outer = _loop_coordinates(dict(sketch["outer_loop"]))
    holes = [
        _loop_coordinates(dict(loop))
        for loop in sketch.get("inner_loops", [])
    ]
    polygon = Polygon(outer, holes=holes)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda item: item.area)
    if not isinstance(polygon, Polygon) or polygon.is_empty:
        raise ParametricReconstructionError(
            "A recovered feature sketch could not be converted to a polygon."
        )
    return polygon


def recipe_solid(recipe: dict[str, Any]) -> trimesh.Trimesh | None:
    """
    Execute the supported recipe subset in its canonical frame.

    Sweep paths need a full CAD kernel and are already evaluated by the
    prismatic recovery module, so residual refinement intentionally starts only
    from simple extrude/revolve bases.
    """
    current: trimesh.Trimesh | None = None
    for feature in recipe.get("features", []):
        feature_type = feature.get("type")
        if feature_type in {"revolve", "revolve_cut"}:
            polygon = sketch_polygon(dict(feature["sketch"]))
            scale = max(
                float(np.max(np.asarray(polygon.exterior.coords)[:, 0])),
                np.finfo(float).eps,
            )
            generated = revolve_profile_solid(
                polygon, tolerance=scale * 1e-3
            )
            if (
                generated is not None
                and feature_type == "revolve_cut"
            ):
                generated = _orient_prism(
                    generated, int(feature.get("direction_index", 2))
                )
        elif feature_type in {"extrude", "cut"}:
            polygon = sketch_polygon(dict(feature["sketch"]))
            try:
                generated = trimesh.creation.extrude_polygon(
                    polygon,
                    height=float(feature["depth"]),
                    engine="earcut",
                )
            except (ImportError, ValueError, RuntimeError, IndexError):
                return None
            generated.apply_translation(
                [0.0, 0.0, float(feature.get("start_offset", 0.0))]
            )
            generated = _orient_prism(
                generated, int(feature.get("direction_index", 2))
            )
        else:
            return None

        generated = as_volume(generated)
        if generated is None:
            return None
        if current is None:
            if feature_type in {"cut", "revolve_cut"}:
                return None
            current = generated
            continue
        try:
            current = (
                trimesh.boolean.difference(
                    [current, generated], engine="manifold"
                )
                if feature_type in {"cut", "revolve_cut"}
                else trimesh.boolean.union(
                    [current, generated], engine="manifold"
                )
            )
        except (ValueError, RuntimeError, IndexError):
            return None
        current = as_volume(current)
        if current is None:
            return None
    return current


def canonical_source(
    mesh: trimesh.Trimesh, recipe: dict[str, Any]
) -> trimesh.Trimesh:
    """Place the source mesh in the canonical frame used by `recipe_solid`."""
    diagnostics = dict(recipe.get("diagnostics", {}))
    frame = diagnostics.get("canonical_frame")
    axis_world = diagnostics.get(
        "revolve_axis_world", diagnostics.get("extrusion_axis_world")
    )
    if not isinstance(frame, dict) or axis_world is None:
        raise ParametricReconstructionError(
            "The recipe does not provide a complete canonical feature frame."
        )
    center = np.asarray(frame["center_world"], dtype=np.float64)
    plane_basis = np.asarray(frame["plane_basis_world"], dtype=np.float64)
    axes = np.column_stack(
        (
            plane_basis[:, 0],
            plane_basis[:, 1],
            np.asarray(axis_world, dtype=np.float64),
        )
    )
    source = canonical_mesh(
        mesh,
        center=center,
        axes=axes,
        axial_index=2,
        axial_low=float(frame["axial_low"]),
    )
    if "revolve_axis_index" in diagnostics:
        offset = np.asarray(
            diagnostics.get("axis_origin_offset", [0.0, 0.0]),
            dtype=np.float64,
        )
        source.apply_translation([-float(offset[0]), -float(offset[1]), 0.0])
    return source


def _difference(
    left: trimesh.Trimesh, right: trimesh.Trimesh
) -> trimesh.Trimesh | None:
    try:
        difference = trimesh.boolean.difference(
            [left, right], engine="manifold"
        )
    except (ValueError, RuntimeError, IndexError):
        return None
    return as_volume(difference)


def _meaningful_components(
    residual: trimesh.Trimesh | None, source_volume: float
) -> list[trimesh.Trimesh]:
    if residual is None:
        return []
    components = [
        component
        for component in residual.split(only_watertight=False)
        if component.is_watertight
        and abs(float(component.volume))
        / max(source_volume, np.finfo(float).eps)
        >= MIN_COMPONENT_VOLUME_FRACTION
    ]
    components.sort(key=lambda item: abs(float(item.volume)), reverse=True)
    return components[:MAX_COMPONENTS_PER_KIND]


def _component_prism(
    component: trimesh.Trimesh,
    *,
    simplify_tolerance: float,
    direction_index: int,
) -> tuple[Polygon, trimesh.Trimesh, float, float] | None:
    vertices = np.asarray(component.vertices, dtype=np.float64)
    planar = [index for index in range(3) if index != direction_index]
    low = float(vertices[:, direction_index].min())
    high = float(vertices[:, direction_index].max())
    depth = high - low
    if depth <= np.finfo(float).eps:
        return None
    polygon = Polygon(vertices[:, planar]).convex_hull
    if not isinstance(polygon, Polygon) or polygon.area <= 0.0:
        return None
    polygon = polygon.simplify(simplify_tolerance, preserve_topology=True)
    if not isinstance(polygon, Polygon) or len(polygon.exterior.coords) < 4:
        return None
    try:
        solid = trimesh.creation.extrude_polygon(
            polygon, height=depth, engine="earcut"
        )
    except (ImportError, ValueError, RuntimeError, IndexError):
        return None
    solid.apply_translation([0.0, 0.0, low])
    solid = _orient_prism(solid, direction_index)
    volume = as_volume(solid)
    if volume is None:
        return None
    return polygon, volume, depth, low


def _candidate_feature(
    polygon: Polygon,
    *,
    feature_type: str,
    depth: float,
    start_offset: float,
    index: int,
    plane: str,
    direction_index: int,
) -> dict[str, Any]:
    role = "residual_boss" if feature_type == "extrude" else "residual_cut"
    label = "Residual Boss" if feature_type == "extrude" else "Residual Cut"
    points = np.asarray(polygon.exterior.coords, dtype=np.float64)[:-1]
    circle = _circle_fit(points)
    if circle is not None:
        outer_loop: dict[str, Any] = {"kind": "circle", **circle}
        constraints = [
            {
                "type": "diameter",
                "value": float(circle["radius"]) * 2.0,
            }
        ]
        center = np.asarray(circle["center"], dtype=np.float64)
        if float(np.linalg.norm(center)) <= float(circle["radius"]) * 0.01:
            constraints.append({"type": "center_coincident_with_origin"})
    else:
        outer_loop = {
            "kind": "polyline",
            "points": _coordinates(polygon.exterior.coords),
        }
        constraints = _polyline_constraints(points)
    return {
        "id": f"{role}-{index}",
        "name": f"CADView {label} {index}",
        "type": feature_type,
        "depth": depth,
        "start_offset": start_offset,
        "direction_index": direction_index,
        "role": role,
        "sketch": {
            "name": f"CADView {label} Profile {index}",
            "plane": plane,
            "outer_loop": outer_loop,
            "inner_loops": [],
            "inferred_constraints": constraints,
        },
    }


def _orient_prism(
    solid: trimesh.Trimesh, direction_index: int
) -> trimesh.Trimesh:
    """Map local profile-X/profile-Y/extrusion-Z into canonical XYZ."""
    if direction_index not in (0, 1, 2):
        raise ParametricReconstructionError(
            f"Residual feature direction must be 0, 1 or 2 (got {direction_index})."
        )
    if direction_index == 2:
        return solid
    planar = [index for index in range(3) if index != direction_index]
    local = np.asarray(solid.vertices, dtype=np.float64)
    canonical = np.empty_like(local)
    canonical[:, planar[0]] = local[:, 0]
    canonical[:, planar[1]] = local[:, 1]
    canonical[:, direction_index] = local[:, 2]
    oriented = trimesh.Trimesh(
        vertices=canonical,
        faces=np.asarray(solid.faces).copy(),
        process=False,
    )
    oriented.process(validate=True)
    if oriented.is_watertight and oriented.volume < 0:
        oriented.invert()
    return oriented


def _feature_plane(base_strategy: str, direction_index: int) -> str:
    if base_strategy == "revolve_reconstruction":
        # Revolve profile maps canonical axial Z to SolidWorks Y.
        return {0: "Right Plane", 1: "Front Plane", 2: "Top Plane"}[
            direction_index
        ]
    return {0: "Right Plane", 1: "Top Plane", 2: "Front Plane"}[
        direction_index
    ]


def _radial_hole_candidates(
    source: trimesh.Trimesh,
    *,
    base_strategy: str,
    feature_index: int,
) -> list[tuple[trimesh.Trimesh, dict[str, Any]]]:
    """Fit principal-direction cylindrical surface patches as native cuts."""
    analysis = analyze_surface_patches(source)
    scale = max(float(np.linalg.norm(source.extents)), np.finfo(float).eps)
    candidates: list[tuple[trimesh.Trimesh, dict[str, Any]]] = []
    for patch in analysis["patches"]:
        if patch.get("surface_type") != "cylinder":
            continue
        fit = patch.get("fit", {})
        axis = np.asarray(fit.get("axis", []), dtype=np.float64)
        center = np.asarray(fit.get("center", []), dtype=np.float64)
        radius = float(fit.get("radius", 0.0))
        height = float(fit.get("height", 0.0))
        if (
            axis.shape != (3,)
            or center.shape != (3,)
            or radius <= scale * 0.002
            or radius >= scale * 0.25
            or height <= scale * 0.002
        ):
            continue
        axis /= max(float(np.linalg.norm(axis)), np.finfo(float).eps)
        direction_index = int(np.argmax(np.abs(axis)))
        alignment = abs(float(axis[direction_index]))
        # The base axis is canonical Z. Its cylinders are the revolve body or
        # axial bore, not radial secondary holes.
        if direction_index == 2 or alignment < RADIAL_AXIS_ALIGNMENT:
            continue
        try:
            cutter = trimesh.creation.cylinder(
                radius=radius, height=height * 1.02, sections=96
            )
            transform = trimesh.geometry.align_vectors(
                [0.0, 0.0, 1.0], axis
            )
            cutter.apply_transform(transform)
            cutter.apply_translation(center)
        except (ValueError, RuntimeError, IndexError):
            continue
        cutter = as_volume(cutter)
        if cutter is None:
            continue
        candidate_index = feature_index + len(candidates)
        planar = [index for index in range(3) if index != direction_index]
        start_offset = float(center[direction_index] - height * 0.51)
        solidworks_center_offset = float(center[direction_index])
        feature = {
            "id": f"radial-hole-{candidate_index}",
            "name": f"CADView Radial Hole {candidate_index}",
            "type": "cut",
            "depth": height * 1.02,
            "start_offset": start_offset,
            "solidworks_start_offset": abs(solidworks_center_offset),
            "flip_start_offset": solidworks_center_offset < 0.0,
            "end_condition": "midplane",
            "direction_index": direction_index,
            "role": "radial_hole",
            "sketch": {
                "name": f"CADView Radial Hole Profile {candidate_index}",
                "plane": _feature_plane(base_strategy, direction_index),
                "outer_loop": {
                    "kind": "circle",
                    "center": [
                        float(center[planar[0]]),
                        float(center[planar[1]]),
                    ],
                    "radius": radius,
                    "fit_normalized_rms": float(
                        fit.get("normalized_rms", 0.0)
                    ),
                },
                "inner_loops": [],
                "inferred_constraints": [
                    {"type": "diameter", "value": radius * 2.0}
                ],
            },
        }
        candidates.append((cutter, feature))
    return candidates


def _revolve_cut_candidate(
    component: trimesh.Trimesh,
    *,
    base_strategy: str,
    axis_index: int,
    feature_id: str,
    display_index: int,
) -> tuple[trimesh.Trimesh, dict[str, Any]] | None:
    fitted = fit_axisymmetric_residual(component, axis_index=axis_index)
    if fitted is None:
        return None
    cutter, polygon, profile = fitted
    cutter = _orient_prism(cutter, axis_index)
    axial_low = float(profile["axial_low"])
    axial_high = float(profile["axial_high"])
    span = max(axial_high - axial_low, np.finfo(float).eps)
    centerline = [
        [0.0, axial_low - span * 0.05],
        [0.0, axial_high + span * 0.05],
    ]
    points = np.asarray(polygon.exterior.coords, dtype=np.float64)[:-1]
    feature = {
        "id": feature_id,
        "name": f"CADView Residual Revolve Cut {display_index}",
        "type": "revolve_cut",
        "angle_degrees": 360.0,
        "direction_index": axis_index,
        "axis": {"kind": "sketch_centerline", "points": centerline},
        "role": "residual_revolve_cut",
        "sketch": {
            "name": f"CADView Residual Revolve Cut Profile {display_index}",
            "plane": (
                "Front Plane"
                if (
                    base_strategy == "revolve_reconstruction"
                    and axis_index == 2
                )
                or (
                    base_strategy == "prismatic_extrusion"
                    and axis_index in {0, 1}
                )
                else "Right Plane"
            ),
            "outer_loop": {
                "kind": "polyline",
                "points": _coordinates(polygon.exterior.coords),
            },
            "inner_loops": [],
            "centerline": centerline,
            "inferred_constraints": _polyline_constraints(points),
        },
        "fit": {
            "roundness": float(profile["roundness"]),
            "roundness_p95": float(profile["roundness_p95"]),
        },
    }
    return cutter, feature


def _polyline_constraints(points: np.ndarray) -> list[dict[str, Any]]:
    """Infer only strong, scale-independent relations for clean sketches."""
    if len(points) < 3:
        return []
    edges = np.roll(points, -1, axis=0) - points
    lengths = np.linalg.norm(edges, axis=1)
    valid = lengths > np.finfo(float).eps
    unit = np.zeros_like(edges)
    unit[valid] = edges[valid] / lengths[valid, None]
    constraints: list[dict[str, Any]] = [
        {"type": "coincident_chain", "closed": True}
    ]
    for index in range(len(points)):
        following = (index + 1) % len(points)
        dot = abs(float(np.dot(unit[index], unit[following])))
        if valid[index] and valid[following] and dot <= 0.01:
            constraints.append(
                {
                    "type": "perpendicular",
                    "entities": [index, following],
                }
            )
    if len(points) == 4:
        for first, second in ((0, 2), (1, 3)):
            determinant = (
                unit[first, 0] * unit[second, 1]
                - unit[first, 1] * unit[second, 0]
            )
            if abs(float(determinant)) <= 0.01:
                constraints.append(
                    {
                        "type": "parallel",
                        "entities": [first, second],
                    }
                )
    return constraints


def _apply_feature(
    current: trimesh.Trimesh,
    generated: trimesh.Trimesh,
    feature_type: str,
) -> trimesh.Trimesh | None:
    try:
        result = (
            trimesh.boolean.difference(
                [current, generated], engine="manifold"
            )
            if feature_type in {"cut", "revolve_cut"}
            else trimesh.boolean.union(
                [current, generated], engine="manifold"
            )
        )
    except (ValueError, RuntimeError, IndexError):
        return None
    return as_volume(result)


def _objective(report: AgreementReport, added_features: int) -> float:
    return (
        report.selection_score
        - FEATURE_COMPLEXITY_PENALTY * added_features
    )


def _state_signature(
    solid: trimesh.Trimesh,
    accepted_ids: frozenset[str],
    depth: int,
    scale: float,
) -> tuple[Any, ...]:
    volume_step = max(scale**3 * 1e-7, 1e-9)
    bounds_step = max(scale * 1e-5, 1e-8)
    bounds = tuple(
        int(round(float(value) / bounds_step))
        for value in np.asarray(solid.bounds).ravel()
    )
    return (
        int(round(abs(float(solid.volume)) / volume_step)),
        bounds,
        depth,
        tuple(sorted(accepted_ids)),
    )


def refine_recipe_with_residuals(
    mesh: trimesh.Trimesh,
    recipe: dict[str, Any],
    unit: LengthUnit,
    *,
    maximum_steps: int = MAX_REFINEMENT_STEPS,
    minimum_improvement: float = MIN_SELECTION_IMPROVEMENT,
    beam_width: int = DEFAULT_BEAM_WIDTH,
) -> dict[str, Any]:
    """
    Iteratively add axial bosses/cuts that measurably improve a base recipe.

    The returned trace records every accepted operation and why the search
    stopped. Unsupported or non-volume inputs return unchanged with an explicit
    diagnostic rather than risking a less reliable CAD model.
    """
    result = deepcopy(recipe)
    diagnostics = dict(result.get("diagnostics", {}))
    beam_width = max(1, min(int(beam_width), 8))
    trace: dict[str, Any] = {
        "attempted": False,
        "accepted_features": [],
        "iterations": [],
        "stop_reason": None,
        "beam_width": beam_width,
    }
    diagnostics["residual_refinement"] = trace
    result["diagnostics"] = diagnostics

    if not boolean_backend_available():
        trace["stop_reason"] = "boolean_backend_unavailable"
        return result
    if result.get("strategy") not in {
        "prismatic_extrusion",
        "revolve_reconstruction",
    }:
        trace["stop_reason"] = "base_strategy_not_supported"
        return result

    source = as_volume(canonical_source(mesh, result))
    current = recipe_solid(result)
    if source is None or current is None:
        trace["stop_reason"] = "source_or_recipe_not_a_volume"
        return result

    trace["attempted"] = True
    source_volume = abs(float(source.volume))
    scale = max(float(np.linalg.norm(source.extents)), np.finfo(float).eps)
    simplify_tolerance = scale * 0.001
    base_strategy = str(result.get("strategy"))
    current_report = evaluate_candidate(source, current)
    base_objective = _objective(current_report, 0)
    radial_holes = _radial_hole_candidates(
        source, base_strategy=base_strategy, feature_index=1
    )
    if (
        current_report.volume_iou is not None
        and current_report.volume_iou >= SATISFIED_VOLUME_IOU
        and not radial_holes
    ):
        trace["stop_reason"] = "agreement_satisfied"
        trace["base_objective"] = base_objective
        return result

    initial_state = _RefinementState(
        solid=current,
        report=current_report,
        added_features=(),
        accepted_ids=frozenset(),
        objective=base_objective,
        ranking_objective=base_objective,
        state_id="base",
    )
    beam = [initial_state]
    best_state = initial_state

    for iteration in range(maximum_steps):
        entering_best = max(beam, key=lambda state: state.ranking_objective)
        children: list[_RefinementState] = []
        candidate_count = 0
        buildable_count = 0
        child_serial = 0
        for parent_index, state in enumerate(beam):
            missing = _difference(source, state.solid)
            excess = _difference(state.solid, source)
            proposals: list[
                tuple[
                    float,
                    AgreementReport,
                    trimesh.Trimesh,
                    dict[str, Any],
                ]
            ] = []
            for kind, residual in (
                ("extrude", missing),
                ("cut", excess),
            ):
                components = _meaningful_components(residual, source_volume)
                for component_index, component in enumerate(components):
                    if kind == "cut":
                        for revolve_axis_index in (2, 0, 1):
                            revolve_feature_id = (
                                "residual-revolve-cut-"
                                f"d{len(state.added_features) + 1}-"
                                f"c{component_index + 1}-"
                                f"a{revolve_axis_index}"
                            )
                            revolved = _revolve_cut_candidate(
                                component,
                                base_strategy=base_strategy,
                                axis_index=revolve_axis_index,
                                feature_id=revolve_feature_id,
                                display_index=len(state.added_features) + 1,
                            )
                            if revolved is not None:
                                generated, feature = revolved
                                candidate = _apply_feature(
                                    state.solid, generated, "revolve_cut"
                                )
                                if candidate is not None:
                                    report = evaluate_candidate(
                                        source, candidate
                                    )
                                    proposals.append(
                                        (
                                            _objective(
                                                report,
                                                len(state.added_features) + 1,
                                            ),
                                            report,
                                            candidate,
                                            feature,
                                        )
                                    )
                    # Prefer the base axis when candidates are equivalent, while
                    # still allowing side-plane operations for asymmetric detail.
                    for direction_index in (2, 0, 1):
                        prism = _component_prism(
                            component,
                            simplify_tolerance=simplify_tolerance,
                            direction_index=direction_index,
                        )
                        if prism is None:
                            continue
                        polygon, generated, depth, start_offset = prism
                        candidate = _apply_feature(
                            state.solid, generated, kind
                        )
                        if candidate is None:
                            continue
                        report = evaluate_candidate(source, candidate)
                        feature = _candidate_feature(
                            polygon,
                            feature_type=kind,
                            depth=depth,
                            start_offset=start_offset,
                            index=len(state.added_features) + 1,
                            plane=_feature_plane(
                                base_strategy, direction_index
                            ),
                            direction_index=direction_index,
                        )
                        feature["id"] = (
                            f"{feature['role']}-"
                            f"d{len(state.added_features) + 1}-"
                            f"c{component_index + 1}-a{direction_index}"
                        )
                        direction_penalty = (
                            0.0
                            if direction_index == 2
                            else OFF_AXIS_COMPLEXITY_PENALTY
                        )
                        proposals.append(
                            (
                                _objective(
                                    report, len(state.added_features) + 1
                                )
                                - direction_penalty,
                                report,
                                candidate,
                                feature,
                            )
                        )
            for cutter, feature_template in radial_holes:
                if feature_template["id"] in state.accepted_ids:
                    continue
                candidate = _apply_feature(state.solid, cutter, "cut")
                if candidate is None:
                    continue
                report = evaluate_candidate(source, candidate)
                proposals.append(
                    (
                        _objective(
                            report, len(state.added_features) + 1
                        ),
                        report,
                        candidate,
                        deepcopy(feature_template),
                    )
                )

            candidate_count += len(proposals)
            buildable_count += len(proposals)
            for ranking, report, candidate, feature in proposals:
                if ranking - state.objective < minimum_improvement:
                    continue
                child_serial += 1
                feature_id = str(feature["id"])
                accepted_ids = state.accepted_ids | {feature_id}
                added_features = state.added_features + (feature,)
                children.append(
                    _RefinementState(
                        solid=candidate,
                        report=report,
                        added_features=added_features,
                        accepted_ids=frozenset(accepted_ids),
                        objective=_objective(report, len(added_features)),
                        ranking_objective=ranking,
                        state_id=f"d{iteration + 1}-s{child_serial}",
                    )
                )

        iteration_report: dict[str, Any] = {
            "iteration": iteration + 1,
            "candidate_count": candidate_count,
            "expanded_parent_count": len(beam),
            "before_score": entering_best.report.score,
            "before_selection_score": (
                entering_best.report.selection_score
            ),
            "beam": [],
        }
        if not children:
            if buildable_count == 0:
                iteration_report["decision"] = "no_buildable_candidates"
                trace["stop_reason"] = "no_buildable_candidates"
            else:
                iteration_report["decision"] = (
                    "rejected_below_improvement_gate"
                )
                trace["stop_reason"] = "improvement_below_gate"
            trace["iterations"].append(iteration_report)
            break

        deduplicated: dict[tuple[Any, ...], _RefinementState] = {}
        for child in children:
            signature = _state_signature(
                child.solid,
                child.accepted_ids,
                len(child.added_features),
                scale,
            )
            incumbent = deduplicated.get(signature)
            if (
                incumbent is None
                or child.ranking_objective > incumbent.ranking_objective
            ):
                deduplicated[signature] = child
        beam = sorted(
            deduplicated.values(),
            key=lambda state: (
                state.ranking_objective,
                state.report.score,
            ),
            reverse=True,
        )[:beam_width]
        layer_best = beam[0]
        objective_best = max(beam, key=lambda state: state.objective)
        if objective_best.objective > best_state.objective:
            best_state = objective_best
        iteration_report["beam"] = [
            {
                "rank": rank,
                "state_id": state.state_id,
                "depth": len(state.added_features),
                "accepted_feature_ids": [
                    str(feature["id"])
                    for feature in state.added_features
                ],
                "last_feature_type": state.added_features[-1]["type"],
                "last_feature_role": state.added_features[-1].get("role"),
                "last_feature_id": state.added_features[-1]["id"],
                "objective": state.objective,
                "agreement": state.report.score,
                "selection_score": state.report.selection_score,
                "execution_kernel": "manifold3d",
                "kernel_valid": True,
            }
            for rank, state in enumerate(beam)
        ]
        improvement = layer_best.ranking_objective - entering_best.objective
        iteration_report.update(
            {
                "best_feature_type": layer_best.added_features[-1]["type"],
                "best_feature_role": layer_best.added_features[-1].get(
                    "role"
                ),
                "best_objective": layer_best.objective,
                "objective_improvement": improvement,
                "after_score": layer_best.report.score,
                "after_selection_score": layer_best.report.selection_score,
            }
        )
        iteration_report["decision"] = "layer_complete"
        trace["iterations"].append(iteration_report)
    else:
        trace["stop_reason"] = "maximum_steps_reached"

    added = len(best_state.added_features)
    if added == 0:
        trace["base_objective"] = base_objective
        return result

    result["features"] = list(result.get("features", [])) + [
        deepcopy(feature) for feature in best_state.added_features
    ]
    trace["accepted_features"] = [
        str(feature["id"]) for feature in best_state.added_features
    ]
    final_report = evaluate_candidate(
        source, best_state.solid, include_residual_regions=True
    )
    diagnostics = dict(result["diagnostics"])
    diagnostics["agreement"] = final_report.as_dict()
    diagnostics["deviation"] = dict(final_report.deviation)
    diagnostics["reconstructed_volume"] = final_report.candidate_volume
    diagnostics["source_volume"] = final_report.source_volume
    diagnostics["volume_error_percent"] = final_report.volume_error_percent
    diagnostics["residual_refinement"] = trace
    result["diagnostics"] = diagnostics
    result["strategy"] = "residual_refined_reconstruction"
    result["confidence"] = final_report.score
    warnings = list(result.get("warnings", []))
    warnings.insert(
        0,
        f"Residual execution loop added {added} native "
        f"{'feature' if added == 1 else 'features'}; volume agreement improved "
        f"from {recipe.get('confidence', 0.0):.3f} to {final_report.score:.3f}.",
    )
    result["warnings"] = warnings
    return result
