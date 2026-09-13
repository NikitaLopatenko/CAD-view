"""
Choose a CAD reconstruction strategy from measured evidence.

The recovery modules each answer a different question - "what if this part is
an extrusion along axis N?", "what if it is a revolve about axis N?" - and each
answer is cheap enough to simply build. Rather than guessing which question is
the right one from a shape heuristic, every hypothesis is constructed, scored
against the source mesh, and the best-agreeing one is returned.

That matters most for the case the old fixed heuristic got wrong: it extruded
along the thinnest principal axis, which turns any tall turned part into a slab
with an arbitrary cross-section.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import trimesh

from parametric_reconstruction import (
    LengthUnit,
    ParametricReconstructionError,
    _right_handed_pca,
    build_prismatic_recipe,
)
from residual_reconstruction import refine_recipe_with_residuals
from revolve_reconstruction import build_revolve_recipe
from solid_agreement import boolean_backend_available
from surface_analysis import analyze_surface_patches

# A hypothesis must beat the incumbent by this much before the strategy flips.
# Two recipes within noise of each other are equally faithful, so the tie goes
# to the simpler prismatic history that the rest of the pipeline handles best.
SELECTION_MARGIN = 0.02
REVOLVE_RADIUS_PERCENTILES = (50.0, 60.0, 75.0, 90.0, 100.0)
REVOLVE_SIMPLIFY_RATIOS = (0.004, 0.01, 0.025)
PROFILE_SIMPLIFICATION_MARGIN = 0.005
MIN_SURFACE_AXIS_AREA_FRACTION = 0.02
SURFACE_AXIS_DUPLICATE_COSINE = 0.9995
MINIMUM_EXPORT_AGREEMENT = 0.60
REFINEMENT_COMPLEXITY_PENALTY = 0.003


def _score_of(recipe: dict[str, Any]) -> float:
    agreement = recipe.get("diagnostics", {}).get("agreement")
    if not isinstance(agreement, dict):
        return 0.0
    score = agreement.get("score")
    return float(score) if score is not None else 0.0


def _selection_score_of(recipe: dict[str, Any]) -> float:
    agreement = recipe.get("diagnostics", {}).get("agreement")
    if not isinstance(agreement, dict):
        return 0.0
    score = agreement.get("selection_score", agreement.get("score"))
    return float(score) if score is not None else 0.0


def recipe_quality(recipe: dict[str, Any]) -> dict[str, Any]:
    """Classify whether a recovered tree is credible enough to export."""
    agreement = _score_of(recipe)
    if agreement >= 0.9:
        status = "high"
    elif agreement >= 0.75:
        status = "usable"
    elif agreement >= MINIMUM_EXPORT_AGREEMENT:
        status = "approximate"
    else:
        status = "unsupported"
    return {
        "status": status,
        "agreement": agreement,
        "minimum_export_agreement": MINIMUM_EXPORT_AGREEMENT,
        "export_recommended": agreement >= MINIMUM_EXPORT_AGREEMENT,
    }


def _summarise(recipe: dict[str, Any], axis: int, kind: str) -> dict[str, Any]:
    diagnostics = recipe.get("diagnostics", {})
    agreement = diagnostics.get("agreement", {})
    return {
        "hypothesis": kind,
        "axis_index": axis,
        "strategy": recipe.get("strategy"),
        "score": _score_of(recipe),
        "selection_score": _selection_score_of(recipe),
        "score_method": agreement.get("method"),
        "volume_iou": agreement.get("volume_iou"),
        "confidence": recipe.get("confidence"),
        "feature_count": len(recipe.get("features", [])),
        "volume_error_percent": agreement.get("volume_error_percent"),
    }


def _default_extrusion_axis(mesh: trimesh.Trimesh) -> int:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    center, axes = _right_handed_pca(vertices)
    return int(np.argmin(np.ptp((vertices - center) @ axes, axis=0)))


def build_recipe(
    mesh: trimesh.Trimesh,
    unit: LengthUnit,
    *,
    simplify_ratio: float = 0.001,
    section_count: int = 25,
    margin: float = SELECTION_MARGIN,
) -> dict[str, object]:
    """
    Build every supported hypothesis for `mesh` and return the best-scoring one.

    Raises if no hypothesis could be constructed at all; individual failures are
    recorded and skipped so one bad axis cannot sink the search.
    """
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ParametricReconstructionError(
            "CAD reconstruction requires a triangle mesh."
        )

    incumbent_axis = _default_extrusion_axis(mesh)
    surface_analysis = analyze_surface_patches(mesh)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    _, pca_axes = _right_handed_pca(vertices)
    surface_axes: list[list[float]] = []
    for patch in surface_analysis["patches"]:
        if (
            patch.get("surface_type") != "cylinder"
            or float(patch.get("area_fraction", 0.0))
            < MIN_SURFACE_AXIS_AREA_FRACTION
        ):
            continue
        fit = patch.get("fit", {})
        axis = np.asarray(fit.get("axis", []), dtype=np.float64)
        if axis.shape != (3,) or float(np.linalg.norm(axis)) <= 0.0:
            continue
        axis /= np.linalg.norm(axis)
        known = [pca_axes[:, index] for index in range(3)]
        known.extend(np.asarray(item, dtype=np.float64) for item in surface_axes)
        if any(
            abs(float(np.dot(axis, candidate)))
            >= SURFACE_AXIS_DUPLICATE_COSINE
            for candidate in known
        ):
            continue
        surface_axes.append([float(value) for value in axis])

    builders: list[
        tuple[
            str,
            int,
            list[float] | None,
            Callable[[], dict[str, object]],
        ]
    ] = []
    for axis in range(3):
        builders.append(
            (
                "prismatic",
                axis,
                None,
                lambda axis=axis: build_prismatic_recipe(
                    mesh,
                    unit,
                    simplify_ratio=simplify_ratio,
                    section_count=section_count,
                    extrusion_index=axis,
                ),
            )
        )
        builders.append(
            (
                "revolve",
                axis,
                None,
                lambda axis=axis: build_revolve_recipe(mesh, unit, axis_index=axis),
            )
        )
    for surface_index, axis_world in enumerate(surface_axes, start=3):
        builders.append(
            (
                "surface_revolve",
                surface_index,
                axis_world,
                lambda axis_world=axis_world: build_revolve_recipe(
                    mesh, unit, axis_world=axis_world
                ),
            )
        )

    evaluated: list[
        tuple[str, int, list[float] | None, dict[str, Any]]
    ] = []
    rejected: list[dict[str, Any]] = []
    for kind, axis, axis_world, build in builders:
        try:
            evaluated.append((kind, axis, axis_world, build()))
        except (
            ParametricReconstructionError,
            ValueError,
            RuntimeError,
            IndexError,
        ) as exc:
            rejected.append(
                {
                    "hypothesis": kind,
                    "axis_index": axis,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )

    if not evaluated:
        detail = "; ".join(item["reason"] for item in rejected) or "unknown"
        raise ParametricReconstructionError(
            f"No CAD hypothesis could be built for this mesh. Detail: {detail}"
        )

    incumbent = next(
        (
            recipe
            for kind, axis, _, recipe in evaluated
            if kind == "prismatic" and axis == incumbent_axis
        ),
        None,
    )
    incumbent_score = (
        _selection_score_of(incumbent) if incumbent is not None else -1.0
    )

    best_kind, best_axis, best = max(
        ((kind, axis, recipe) for kind, axis, _, recipe in evaluated),
        key=lambda item: _selection_score_of(item[2]),
    )
    best_prismatic = max(
        (
            (kind, axis, recipe)
            for kind, axis, _, recipe in evaluated
            if kind == "prismatic"
        ),
        key=lambda item: _selection_score_of(item[2]),
        default=None,
    )
    # Equifinality is resolved by parsimony: if the strongest prismatic model
    # is geometrically indistinguishable from the winner, retain the simpler
    # sketch-extrude history. Do not anchor this decision to the legacy
    # thinnest-axis guess; a cylinder's valid extrusion axis is its longest.
    if (
        best_prismatic is not None
        and _selection_score_of(best)
        <= _selection_score_of(best_prismatic[2]) + margin
    ):
        best_kind, best_axis, best = best_prismatic
    best_axis_world = next(
        axis_world
        for kind, axis, axis_world, recipe in evaluated
        if kind == best_kind and axis == best_axis and recipe is best
    )

    hypotheses = [
        {
            **_summarise(recipe, axis, kind),
            "selected": recipe is best,
        }
        for kind, axis, _, recipe in evaluated
    ]
    hypotheses.sort(key=lambda item: item["score"], reverse=True)

    # CADReasoner-style residual evidence is expensive and only actionable for
    # the selected current build, so compute connected missing/excess regions
    # once after ranking instead of for all six hypotheses.
    parameter_refinement: dict[str, Any] | None = None
    if best_kind in {"revolve", "surface_revolve"}:
        revolve_axis_arguments: dict[str, Any] = (
            {"axis_world": best_axis_world}
            if best_axis_world is not None
            else {"axis_index": best_axis}
        )
        revolve_variants: list[tuple[float, dict[str, Any]]] = []
        for percentile in REVOLVE_RADIUS_PERCENTILES:
            if percentile == 90.0:
                variant = best
            else:
                variant = build_revolve_recipe(
                    mesh,
                    unit,
                    outer_radius_percentile=percentile,
                    **revolve_axis_arguments,
                )
            revolve_variants.append((percentile, variant))
        selected_percentile, best = max(
            revolve_variants,
            key=lambda item: _selection_score_of(item[1]),
        )
        simplify_variants: list[tuple[float, dict[str, Any]]] = []
        for simplify_ratio_variant in REVOLVE_SIMPLIFY_RATIOS:
            if simplify_ratio_variant == 0.004:
                variant = best
            else:
                variant = build_revolve_recipe(
                    mesh,
                    unit,
                    outer_radius_percentile=selected_percentile,
                    simplify_ratio=simplify_ratio_variant,
                    **revolve_axis_arguments,
                )
            simplify_variants.append((simplify_ratio_variant, variant))
        best_simplify_score = max(
            _selection_score_of(variant)
            for _, variant in simplify_variants
        )
        simplify_eligible = [
            item
            for item in simplify_variants
            if _selection_score_of(item[1])
            >= best_simplify_score - PROFILE_SIMPLIFICATION_MARGIN
        ]
        selected_simplify_ratio, best = min(
            simplify_eligible,
            key=lambda item: int(
                item[1]
                .get("diagnostics", {})
                .get("profile_point_count", 1_000_000)
            ),
        )
        parameter_refinement = {
            "parameter": "outer_radius_percentile",
            "selected": selected_percentile,
            "candidates": [
                {
                    "value": percentile,
                    "volume_iou": _score_of(variant),
                    "selection_score": _selection_score_of(variant),
                }
                for percentile, variant in revolve_variants
            ],
            "profile_simplification": {
                "selected": selected_simplify_ratio,
                "selection_margin": PROFILE_SIMPLIFICATION_MARGIN,
                "candidates": [
                    {
                        "value": simplify_ratio_variant,
                        "volume_iou": _score_of(variant),
                        "selection_score": _selection_score_of(variant),
                        "profile_point_count": int(
                            variant.get("diagnostics", {}).get(
                                "profile_point_count", 0
                            )
                        ),
                    }
                    for simplify_ratio_variant, variant in simplify_variants
                ],
            },
        }
        selected = build_revolve_recipe(
            mesh,
            unit,
            include_residual_regions=True,
            outer_radius_percentile=selected_percentile,
            simplify_ratio=selected_simplify_ratio,
            **revolve_axis_arguments,
        )
    else:
        selected = build_prismatic_recipe(
            mesh,
            unit,
            simplify_ratio=simplify_ratio,
            section_count=section_count,
            extrusion_index=best_axis,
            include_residual_regions=True,
        )
    if parameter_refinement is not None:
        selected_diagnostics = dict(selected.get("diagnostics", {}))
        selected_diagnostics["parameter_refinement"] = parameter_refinement
        selected["diagnostics"] = selected_diagnostics

    # A high-scoring simple base can be a dead end while a weaker axis becomes
    # nearly exact after two or three native features. Preserve all prismatic
    # base axes until residual execution has had a chance to refine them.
    refinement_seeds: list[
        tuple[str, int, list[float] | None, dict[str, Any]]
    ] = [(best_kind, best_axis, best_axis_world, selected)]
    for kind, axis, axis_world, recipe in evaluated:
        if kind != "prismatic" or (
            kind == best_kind and axis == best_axis
        ):
            continue
        refinement_seeds.append((kind, axis, axis_world, recipe))

    refined_hypotheses: list[
        tuple[str, int, list[float] | None, dict[str, Any]]
    ] = []
    for kind, axis, axis_world, seed in refinement_seeds:
        refined_hypotheses.append(
            (
                kind,
                axis,
                axis_world,
                refine_recipe_with_residuals(mesh, seed, unit),
            )
        )

    def refined_objective(item: tuple[str, int, list[float] | None, dict[str, Any]]) -> float:
        feature_count = len(item[3].get("features", []))
        return _selection_score_of(item[3]) - (
            REFINEMENT_COMPLEXITY_PENALTY * max(feature_count - 1, 0)
        )

    best_kind, best_axis, best_axis_world, selected = max(
        refined_hypotheses, key=refined_objective
    )
    selected = dict(selected)
    refined_by_key = {
        (kind, axis): recipe
        for kind, axis, _, recipe in refined_hypotheses
    }
    for hypothesis in hypotheses:
        key = (hypothesis["hypothesis"], hypothesis["axis_index"])
        refined = refined_by_key.get(key)
        hypothesis["selected"] = key == (best_kind, best_axis)
        if refined is None:
            continue
        refined_agreement = refined.get("diagnostics", {}).get(
            "agreement", {}
        )
        hypothesis.update(
            {
                "strategy": refined.get("strategy"),
                "score": _score_of(refined),
                "selection_score": _selection_score_of(refined),
                "volume_iou": refined_agreement.get("volume_iou"),
                "confidence": refined.get("confidence"),
                "feature_count": len(refined.get("features", [])),
                "volume_error_percent": refined_agreement.get(
                    "volume_error_percent"
                ),
            }
        )
    hypotheses.sort(
        key=lambda item: float(item["selection_score"]), reverse=True
    )
    diagnostics = dict(selected.get("diagnostics", {}))
    diagnostics["surface_analysis"] = surface_analysis
    diagnostics["hypothesis_search"] = {
        "selected": {
            "hypothesis": best_kind,
            "axis_index": best_axis,
            "axis_world": best_axis_world,
        },
        "score_method": (
            "volume_iou" if boolean_backend_available() else "surface_deviation"
        ),
        "selection_margin": margin,
        "incumbent": {
            "hypothesis": "prismatic",
            "axis_index": incumbent_axis,
            "score": incumbent_score if incumbent is not None else None,
        },
        "hypotheses": hypotheses,
        "rejected": rejected,
    }
    quality = recipe_quality(selected)
    diagnostics["quality"] = quality
    selected["diagnostics"] = diagnostics

    warnings = list(selected.get("warnings", []))
    if not quality["export_recommended"]:
        warnings.insert(
            0,
            f"Reconstruction agreement is only {quality['agreement']:.3f}; "
            "native CAD export is blocked because every current feature-tree "
            f"hypothesis is below {MINIMUM_EXPORT_AGREEMENT:.2f}.",
        )
    runner_up = next(
        (item for item in hypotheses if not item["selected"]), None
    )
    if runner_up is not None:
        warnings.insert(
            0,
            f"Chose {best_kind} axis {best_axis} "
            f"(agreement {_score_of(selected):.3f}, ranked "
            f"{_selection_score_of(selected):.3f}) over "
            f"{runner_up['hypothesis']} axis {runner_up['axis_index']} "
            f"(agreement {runner_up['score']:.3f}, ranked "
            f"{runner_up['selection_score']:.3f}) from "
            f"{len(hypotheses)} scored hypotheses.",
        )
    if not boolean_backend_available():
        warnings.append(
            "No boolean kernel is installed, so hypotheses were ranked by "
            "surface deviation instead of volume IoU. Install manifold3d for "
            "exact agreement scoring."
        )
    selected["warnings"] = warnings
    return selected
