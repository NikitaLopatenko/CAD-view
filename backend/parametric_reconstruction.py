from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tempfile
import winreg
from pathlib import Path
from typing import Any, Literal

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon

LengthUnit = Literal["mm", "cm", "m", "in"]

UNIT_TO_METERS: dict[LengthUnit, float] = {
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "in": 0.0254,
}


class ParametricReconstructionError(ValueError):
    pass


def _right_handed_pca(vertices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    center = vertices.mean(axis=0)
    covariance = np.cov((vertices - center).T)
    _, axes = np.linalg.eigh(covariance)
    left, _, right = np.linalg.svd(axes)
    axes = left @ right
    if np.linalg.det(axes) < 0:
        axes[:, 0] *= -1
    return center, axes


def _coordinates(points: Any) -> list[list[float]]:
    coordinates = np.asarray(points, dtype=np.float64)
    if len(coordinates) > 1 and np.allclose(coordinates[0], coordinates[-1]):
        coordinates = coordinates[:-1]
    return [[float(x), float(y)] for x, y in coordinates]


def _circle_fit(points: np.ndarray) -> dict[str, object] | None:
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 6:
        return None
    x = points[:, 0]
    y = points[:, 1]
    matrix = np.column_stack((2.0 * x, 2.0 * y, np.ones(len(points))))
    rhs = np.square(x) + np.square(y)
    center_x, center_y, constant = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
    radius_squared = constant + center_x**2 + center_y**2
    if radius_squared <= 0:
        return None
    radius = float(np.sqrt(radius_squared))
    radial = np.linalg.norm(
        points - np.array([center_x, center_y], dtype=np.float64), axis=1
    )
    rms = float(np.sqrt(np.mean(np.square(radial - radius))))
    normalized = rms / max(radius, np.finfo(np.float64).eps)
    if normalized > 0.015:
        return None
    return {
        "kind": "circle",
        "center": [float(center_x), float(center_y)],
        "radius": radius,
        "fit_normalized_rms": normalized,
    }


def _section_polygon(
    mesh: trimesh.Trimesh,
    *,
    center: np.ndarray,
    normal: np.ndarray,
    plane_basis: np.ndarray,
    axial_position: float,
) -> Polygon | None:
    origin = center + normal * axial_position
    section = mesh.section(plane_origin=origin, plane_normal=normal)
    if section is None:
        return None

    rings: list[Polygon] = []
    for discrete in section.discrete:
        points = np.asarray(discrete, dtype=np.float64)
        if len(points) < 4:
            continue
        projected = (points - center) @ plane_basis
        ring = Polygon(projected)
        if ring.is_valid and ring.area > 1e-10:
            rings.append(ring)
    if not rings:
        return None

    outer = max(rings, key=lambda candidate: candidate.area)
    holes = [
        ring.exterior.coords
        for ring in rings
        if ring is not outer and outer.contains(ring.representative_point())
    ]
    polygon = Polygon(outer.exterior.coords, holes=holes)
    return polygon if polygon.is_valid and not polygon.is_empty else outer


def _profile_sketch(
    polygon: Polygon,
    *,
    name: str,
    tolerance: float,
) -> tuple[dict[str, object], Polygon]:
    simplified = polygon.simplify(tolerance, preserve_topology=True)
    if simplified.is_empty or not simplified.is_valid or not isinstance(
        simplified, Polygon
    ):
        simplified = polygon

    outer = _coordinates(simplified.exterior.coords)
    if len(outer) < 3:
        raise ParametricReconstructionError(
            "An extracted profile has fewer than three points."
        )

    inner_loops: list[dict[str, object]] = []
    for ring in simplified.interiors:
        raw = np.asarray(ring.coords, dtype=np.float64)
        open_ring = raw[:-1] if np.allclose(raw[0], raw[-1]) else raw
        circle = _circle_fit(open_ring)
        inner_loops.append(
            circle
            if circle is not None
            else {"kind": "polyline", "points": _coordinates(ring.coords)}
        )
    return (
        {
            "name": name,
            "plane": "Front Plane",
            "outer_loop": {"kind": "polyline", "points": outer},
            "inner_loops": inner_loops,
        },
        simplified,
    )


def _relative_profile_difference(first: Polygon, second: Polygon) -> float:
    denominator = max((first.area + second.area) * 0.5, 1e-12)
    return float(first.symmetric_difference(second).area / denominator)


def _geometry_points_2d(geometry: Any) -> list[np.ndarray]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [np.asarray(geometry.coords[0], dtype=np.float64)]
    if hasattr(geometry, "geoms"):
        points: list[np.ndarray] = []
        for child in geometry.geoms:
            points.extend(_geometry_points_2d(child))
        return points
    if hasattr(geometry, "coords"):
        return [
            np.asarray(coordinate, dtype=np.float64)
            for coordinate in geometry.coords
        ]
    return []


def _close_short_circular_gaps(mask: np.ndarray, maximum_gap: int = 4) -> np.ndarray:
    result = np.asarray(mask, dtype=bool).copy()
    count = len(result)
    if count == 0 or result.all() or not result.any():
        return result
    doubled = np.concatenate((result, result))
    index = 0
    while index < len(doubled):
        if doubled[index]:
            index += 1
            continue
        end = index
        while end < len(doubled) and not doubled[end]:
            end += 1
        if (
            end - index <= maximum_gap
            and index > 0
            and end < len(doubled)
            and doubled[index - 1]
            and doubled[end]
        ):
            for fill in range(index, end):
                result[fill % count] = True
        index = end
    return result


def _longest_circular_run(mask: np.ndarray) -> list[int]:
    values = np.asarray(mask, dtype=bool)
    count = len(values)
    if count == 0 or not values.any():
        return []
    if values.all():
        return list(range(count))
    doubled = np.concatenate((values, values))
    best_start = 0
    best_length = 0
    start = 0
    while start < len(doubled):
        if not doubled[start]:
            start += 1
            continue
        end = start
        while end < len(doubled) and doubled[end] and end - start < count:
            end += 1
        if end - start > best_length:
            best_start = start
            best_length = end - start
        start = end
    return [(best_start + offset) % count for offset in range(best_length)]


def _orthogonal_sweep_hypothesis(
    *,
    side_polygon: Polygon,
    sections: list[tuple[float, Polygon]],
    depth: float,
    planar_span: float,
    station_count: int = 96,
) -> dict[str, object] | None:
    """
    Compare a constant orthogonal sweep section with a stacked axial cut.

    Rays fired inward from the outer path measure groove depth at every axial
    section. A true sweep produces the same depth-vs-axial profile along a
    contiguous path; a 2.5D cut instead needs a different radial depth at each
    path station.
    """
    boundary = side_polygon.exterior
    fractions = np.asarray([item[0] for item in sections], dtype=np.float64)
    polygons = [item[1] for item in sections]
    matrix = np.full((station_count, len(polygons)), np.nan, dtype=np.float64)
    turning = np.full(station_count, np.inf, dtype=np.float64)
    path_points = np.zeros((station_count, 2), dtype=np.float64)
    inward_normals = np.zeros((station_count, 2), dtype=np.float64)
    ray_length = planar_span * 1.5
    probe = max(planar_span * 1e-4, 1e-8)
    delta = 2.0 / station_count

    for station in range(station_count):
        fraction = station / station_count
        point = np.asarray(
            boundary.interpolate(fraction, normalized=True).coords[0],
            dtype=np.float64,
        )
        before = np.asarray(
            boundary.interpolate((fraction - delta) % 1.0, normalized=True).coords[0],
            dtype=np.float64,
        )
        after = np.asarray(
            boundary.interpolate((fraction + delta) % 1.0, normalized=True).coords[0],
            dtype=np.float64,
        )
        tangent = after - before
        tangent_length = float(np.linalg.norm(tangent))
        if tangent_length <= 1e-12:
            continue
        tangent /= tangent_length
        inward = np.array([-tangent[1], tangent[0]], dtype=np.float64)
        if not side_polygon.buffer(probe * 0.1).contains(
            Point(*(point + inward * probe))
        ):
            inward *= -1.0

        near_before = np.asarray(
            boundary.interpolate(
                (fraction - delta * 0.5) % 1.0, normalized=True
            ).coords[0],
            dtype=np.float64,
        )
        near_after = np.asarray(
            boundary.interpolate(
                (fraction + delta * 0.5) % 1.0, normalized=True
            ).coords[0],
            dtype=np.float64,
        )
        first = point - near_before
        second = near_after - point
        first /= max(float(np.linalg.norm(first)), 1e-12)
        second /= max(float(np.linalg.norm(second)), 1e-12)
        turning[station] = float(
            np.arccos(np.clip(np.dot(first, second), -1.0, 1.0))
        )
        path_points[station] = point
        inward_normals[station] = inward

        ray = LineString(
            [
                point - inward * max(planar_span * 0.05, probe * 3.0),
                point + inward * ray_length,
            ]
        )
        for section_index, polygon in enumerate(polygons):
            intersections = _geometry_points_2d(ray.intersection(polygon.exterior))
            projected = [
                float(np.dot(candidate - point, inward))
                for candidate in intersections
            ]
            if projected:
                nearest = min(projected, key=abs)
                if nearest >= -planar_span * 0.02:
                    matrix[station, section_index] = max(0.0, nearest)
                else:
                    forward = [distance for distance in projected if distance >= 0]
                    if forward:
                        matrix[station, section_index] = min(forward)

    finite_fraction = np.isfinite(matrix).mean(axis=1)
    station_depth = np.nanmax(
        np.where(np.isfinite(matrix), matrix, -np.inf), axis=1
    )
    active = station_depth > planar_span * 0.002
    smooth = turning < np.radians(25.0)
    usable = finite_fraction >= 0.85
    candidates = station_depth[active & smooth & usable]
    if len(candidates) < max(8, station_count // 8):
        return None

    ordered = np.sort(candidates)
    log_gaps = np.diff(np.log(np.maximum(ordered, 1e-12)))
    if len(log_gaps) and float(np.max(log_gaps)) > np.log(2.0):
        split = int(np.argmax(log_gaps))
        cluster_threshold = float(
            np.sqrt(ordered[split] * ordered[split + 1])
        )
    else:
        cluster_threshold = float(np.median(ordered) * 2.0)

    dominant = active & smooth & usable & (station_depth <= cluster_threshold)
    dominant = _close_short_circular_gaps(dominant, maximum_gap=4)
    run = _longest_circular_run(dominant)
    if len(run) < max(8, int(station_count * 0.25)):
        return None

    run_matrix = matrix[run].copy()
    column_median = np.nanmedian(run_matrix, axis=0)
    missing_rows, missing_columns = np.where(~np.isfinite(run_matrix))
    run_matrix[missing_rows, missing_columns] = column_median[missing_columns]
    median_profile = np.median(run_matrix, axis=0)
    maximum_depth = float(np.max(median_profile))
    if maximum_depth <= planar_span * 0.002:
        return None

    sweep_station_rms = np.sqrt(
        np.mean(np.square(run_matrix - median_profile), axis=1)
    )
    sweep_rms = float(np.median(sweep_station_rms))

    active_profile = median_profile > maximum_depth * 0.12
    if not active_profile.any():
        return None
    rectangular = active_profile.astype(np.float64)
    amplitudes = (
        np.sum(run_matrix * rectangular, axis=1)
        / max(float(np.sum(np.square(rectangular))), 1e-12)
    )
    stacked_prediction = amplitudes[:, None] * rectangular[None, :]
    stacked_station_rms = np.sqrt(
        np.mean(np.square(run_matrix - stacked_prediction), axis=1)
    )
    stacked_rms = float(np.median(stacked_station_rms))
    normalized_sweep_rms = sweep_rms / maximum_depth
    normalized_stacked_rms = stacked_rms / maximum_depth
    coverage = len(run) / station_count

    path_offset = maximum_depth * 0.5
    path = path_points[run] + inward_normals[run] * path_offset
    tangent = path[1] - path[0]
    tangent /= max(float(np.linalg.norm(tangent)), 1e-12)
    rotation = float(np.pi / 2.0 - np.arctan2(tangent[1], tangent[0]))
    cosine = float(np.cos(rotation))
    sine = float(np.sin(rotation))
    rotation_matrix = np.array(
        [[cosine, -sine], [sine, cosine]], dtype=np.float64
    )
    rotated_path = path @ rotation_matrix.T
    translated_y = float(rotated_path[0, 1])
    rotated_path[:, 1] -= translated_y
    rotated_inward = inward_normals[run[0]] @ rotation_matrix.T
    radial_sign = 1.0 if rotated_inward[0] >= 0.0 else -1.0

    path_line = LineString(rotated_path).simplify(
        max(planar_span * 0.00075, 1e-7), preserve_topology=False
    )
    simplified_path = np.asarray(path_line.coords, dtype=np.float64)
    path_start_x = float(simplified_path[0, 0])
    outer_profile_x = path_start_x - radial_sign * path_offset

    axial = (fractions - 0.5) * depth
    active_indices = np.flatnonzero(median_profile > maximum_depth * 0.01)
    profile_start = max(int(active_indices[0]) - 1, 0)
    profile_end = min(int(active_indices[-1]) + 1, len(axial) - 1)
    profile_axial = axial[profile_start : profile_end + 1]
    profile_depth = median_profile[profile_start : profile_end + 1].copy()
    profile_depth[0] = 0.0
    profile_depth[-1] = 0.0
    profile_points: list[list[float]] = [
        [outer_profile_x, float(profile_axial[0])],
        [outer_profile_x, float(profile_axial[-1])],
    ]
    for axial_value, radial_depth in reversed(
        list(zip(profile_axial, profile_depth, strict=True))
    ):
        profile_points.append(
            [
                outer_profile_x + radial_sign * float(radial_depth),
                float(axial_value),
            ]
        )

    sweep_score = normalized_sweep_rms + 0.01
    stacked_score = normalized_stacked_rms + 0.02
    score_delta = abs(sweep_score - stacked_score)
    if score_delta < 0.03:
        decision = "ambiguous_equivalent"
    elif sweep_score < stacked_score:
        decision = (
            "sweep_preferred"
            if score_delta >= 0.10
            else "sweep_preferred_low_confidence"
        )
    else:
        decision = (
            "stacked_preferred"
            if score_delta >= 0.10
            else "stacked_preferred_low_confidence"
        )
    selected = (
        coverage >= 0.40
        and normalized_sweep_rms <= 0.08
        and sweep_score < stacked_score * 0.75
        and decision in {"sweep_preferred", "sweep_preferred_low_confidence"}
    )
    return {
        "selected": selected,
        "decision": decision,
        "score_delta": float(score_delta),
        "coverage": float(coverage),
        "station_count": int(len(run)),
        "profile_sample_count": int(len(median_profile)),
        "maximum_depth": maximum_depth,
        "path_offset": float(path_offset),
        "sweep_rms": sweep_rms,
        "sweep_normalized_rms": float(normalized_sweep_rms),
        "stacked_rms": stacked_rms,
        "stacked_normalized_rms": float(normalized_stacked_rms),
        "hypotheses": [
            {
                "type": "sweep_cut",
                "score": float(sweep_score),
                "deviation_rms": sweep_rms,
                "complexity_penalty": 0.01,
            },
            {
                "type": "stacked_cut",
                "score": float(stacked_score),
                "deviation_rms": stacked_rms,
                "complexity_penalty": 0.02,
            },
        ],
        "rotation_radians": rotation,
        "translation_y": -translated_y,
        "path_points": _coordinates(simplified_path),
        "profile_points": profile_points,
        "profile_depth_samples": [float(value) for value in median_profile],
        "axial_samples": [float(value) for value in axial],
    }


def _transform_planar_polygon(
    polygon: Polygon, rotation_radians: float, translation_y: float
) -> Polygon:
    transformed = affinity.rotate(
        polygon,
        rotation_radians,
        origin=(0.0, 0.0),
        use_radians=True,
    )
    return affinity.translate(transformed, yoff=translation_y)


def _curvature_segmentation_evidence(
    mesh: trimesh.Trimesh,
    *,
    center: np.ndarray,
    normal: np.ndarray,
    plane_basis: np.ndarray,
    axial_low: float,
    depth: float,
) -> dict[str, float | int]:
    angles = np.asarray(mesh.face_adjacency_angles, dtype=np.float64)
    convex = np.asarray(mesh.face_adjacency_convex, dtype=bool)
    if len(angles):
        histogram, edges = np.histogram(angles, bins=64)
        probabilities = histogram.astype(np.float64) / max(histogram.sum(), 1)
        cumulative_weight = np.cumsum(probabilities)
        centers = (edges[:-1] + edges[1:]) * 0.5
        cumulative_mean = np.cumsum(probabilities * centers)
        total_mean = cumulative_mean[-1]
        denominator = cumulative_weight * (1.0 - cumulative_weight)
        between = np.divide(
            np.square(total_mean * cumulative_weight - cumulative_mean),
            denominator,
            out=np.zeros_like(denominator),
            where=denominator > 1e-12,
        )
        sharp_threshold = float(centers[int(np.argmax(between))])
        sharp = angles >= max(sharp_threshold, np.radians(3.0))
        sharp_count = int(np.count_nonzero(sharp))
        concave_sharp = int(np.count_nonzero(sharp & ~convex))
    else:
        sharp_threshold = 0.0
        sharp_count = 0
        concave_sharp = 0

    face_centers = np.asarray(mesh.triangles_center, dtype=np.float64)
    axial = (face_centers - center) @ normal - axial_low
    central_band = np.abs(axial / max(depth, 1e-12) - 0.5) <= 0.22
    local_normals = np.asarray(mesh.face_normals, dtype=np.float64) @ plane_basis
    radial_norm = np.linalg.norm(local_normals, axis=1)
    central_faces = int(np.count_nonzero(central_band))
    radial_central = int(np.count_nonzero(central_band & (radial_norm >= 0.7)))
    return {
        "otsu_sharp_angle_degrees": float(np.degrees(sharp_threshold)),
        "sharp_adjacency_count": sharp_count,
        "concave_sharp_adjacency_count": concave_sharp,
        "concave_fraction_of_sharp": float(
            concave_sharp / max(sharp_count, 1)
        ),
        "central_band_face_count": central_faces,
        "radial_normal_fraction_in_central_band": float(
            radial_central / max(central_faces, 1)
        ),
    }


def _source_to_cad_deviation(
    mesh: trimesh.Trimesh,
    *,
    center: np.ndarray,
    axes: np.ndarray,
    extrusion_index: int,
    axial_low: float,
    components: list[tuple[Polygon, float, float]],
) -> dict[str, float | int | None]:
    try:
        solids: list[trimesh.Trimesh] = []
        for polygon, depth, start_offset in components:
            solid = trimesh.creation.extrude_polygon(
                polygon,
                height=depth,
                engine="earcut",
            )
            solid.apply_translation([0.0, 0.0, start_offset])
            solids.append(solid)
        reconstructed = trimesh.util.concatenate(solids)

        points = np.vstack(
            (
                np.asarray(mesh.vertices, dtype=np.float64),
                np.asarray(mesh.triangles_center, dtype=np.float64),
            )
        )
        if len(points) > 20_000:
            indices = np.linspace(0, len(points) - 1, 20_000, dtype=np.int64)
            points = points[indices]

        local = (points - center) @ axes
        planar_indices = [
            index for index in range(3) if index != extrusion_index
        ]
        canonical = np.column_stack(
            (
                local[:, planar_indices[0]],
                local[:, planar_indices[1]],
                local[:, extrusion_index] - axial_low,
            )
        )
        _, distances, _ = trimesh.proximity.closest_point(
            reconstructed, canonical
        )
        finite = distances[np.isfinite(distances)]
        if len(finite) == 0:
            raise ValueError("No finite deviation samples.")
        return {
            "sample_count": int(len(finite)),
            "mean": float(np.mean(finite)),
            "rms": float(np.sqrt(np.mean(np.square(finite)))),
            "p95": float(np.percentile(finite, 95)),
            "max": float(np.max(finite)),
        }
    except (ImportError, ValueError, RuntimeError):
        return {
            "sample_count": 0,
            "mean": None,
            "rms": None,
            "p95": None,
            "max": None,
        }


def build_prismatic_recipe(
    mesh: trimesh.Trimesh,
    unit: LengthUnit,
    *,
    simplify_ratio: float = 0.001,
    section_count: int = 25,
) -> dict[str, object]:
    """
    Recover an editable feature recipe from a mostly prismatic mesh.

    Multi-section sampling detects symmetric perimeter grooves that a single
    center slice misses. The groove is represented as a full outer extrude plus
    a native cut of the recovered ring; diagnostics retain the sweep path for
    future constant-profile Sweep-Cut generation.
    """
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ParametricReconstructionError(
            "Parametric reconstruction requires a triangle mesh."
        )

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    center, axes = _right_handed_pca(vertices)
    local = (vertices - center) @ axes
    spans = np.ptp(local, axis=0)
    extrusion_index = int(np.argmin(spans))
    other = [index for index in range(3) if index != extrusion_index]
    axial_low = float(local[:, extrusion_index].min())
    axial_high = float(local[:, extrusion_index].max())
    depth = float(spans[extrusion_index])
    planar_span = float(max(spans[other]))
    thinness_ratio = depth / max(
        float(min(spans[other])), np.finfo(np.float64).eps
    )

    normal = axes[:, extrusion_index]
    plane_basis = axes[:, other]
    fractions = np.linspace(0.03, 0.97, max(section_count, 9))
    sections: list[tuple[float, Polygon]] = []
    for fraction in fractions:
        polygon = _section_polygon(
            mesh,
            center=center,
            normal=normal,
            plane_basis=plane_basis,
            axial_position=axial_low + depth * float(fraction),
        )
        if polygon is not None:
            sections.append((float(fraction), polygon))
    if len(sections) < 5:
        raise ParametricReconstructionError(
            "Could not recover enough closed cross-sections through this mesh."
        )

    center_fraction, center_polygon = min(
        sections, key=lambda item: abs(item[0] - 0.5)
    )
    left_fraction, left_polygon = min(
        sections, key=lambda item: abs(item[0] - 0.06)
    )
    right_fraction, right_polygon = min(
        sections, key=lambda item: abs(item[0] - 0.94)
    )
    side_polygon = max(
        (left_polygon, right_polygon), key=lambda candidate: candidate.area
    )

    tolerance = max(planar_span * simplify_ratio, 1e-7)
    core_sketch, core_polygon = _profile_sketch(
        center_polygon,
        name="CADView Core Profile",
        tolerance=tolerance,
    )
    side_sketch, simplified_side_polygon = _profile_sketch(
        side_polygon,
        name="CADView Outer Profile",
        tolerance=tolerance,
    )

    profile_area = float(core_polygon.area)
    side_area = float(simplified_side_polygon.area)
    side_difference = max(side_area - profile_area, 0.0)
    side_symmetry_error = _relative_profile_difference(
        left_polygon, right_polygon
    )
    center_outside_side_fraction = float(
        center_polygon.difference(side_polygon).area
        / max(center_polygon.area, 1e-12)
    )
    variation_fraction = side_difference / max(profile_area, 1e-12)
    groove_detected = (
        variation_fraction > 0.015
        and side_symmetry_error < 0.04
        and center_outside_side_fraction < 0.02
    )
    sweep_analysis = (
        _orthogonal_sweep_hypothesis(
            side_polygon=simplified_side_polygon,
            sections=sections,
            depth=depth,
            planar_span=planar_span,
        )
        if groove_detected
        else None
    )
    sweep_selected = bool(
        sweep_analysis is not None and sweep_analysis.get("selected")
    )

    flange_depth = 0.0
    groove_width = 0.0
    sweep_candidates: list[dict[str, object]] = []

    if groove_detected:
        side_target = center_polygon.area + 0.85 * (
            side_polygon.area - center_polygon.area
        )
        left_plateau = [
            fraction
            for fraction, polygon in sections
            if fraction <= center_fraction and polygon.area >= side_target
        ]
        right_plateau = [
            fraction
            for fraction, polygon in sections
            if fraction >= center_fraction and polygon.area >= side_target
        ]
        left_boundary = max(left_plateau, default=0.25)
        right_boundary = min(right_plateau, default=0.75)
        flange_fraction = float(
            np.clip(
                (left_boundary + (1.0 - right_boundary)) * 0.5,
                0.05,
                0.45,
            )
        )
        flange_depth = depth * flange_fraction
        groove_width = max(depth - 2.0 * flange_depth, 0.0)

        components: list[tuple[Polygon, float, float]] = [
            (simplified_side_polygon, flange_depth, 0.0),
            (core_polygon, groove_width, flange_depth),
            (
                simplified_side_polygon,
                flange_depth,
                flange_depth + groove_width,
            ),
        ]
        average_radial_depth = side_difference / max(
            center_polygon.exterior.length, 1e-12
        )
        if sweep_selected and sweep_analysis is not None:
            rotation = float(sweep_analysis["rotation_radians"])
            translation_y = float(sweep_analysis["translation_y"])
            transformed_side = _transform_planar_polygon(
                simplified_side_polygon, rotation, translation_y
            )
            transformed_side_sketch, _ = _profile_sketch(
                transformed_side,
                name="CADView Outer Profile",
                tolerance=tolerance,
            )
            sweep_profile_points = list(sweep_analysis["profile_points"])
            sweep_profile_polygon = Polygon(sweep_profile_points)
            if not sweep_profile_polygon.is_valid or sweep_profile_polygon.is_empty:
                raise ParametricReconstructionError(
                    "The orthogonal sweep profile is not a valid closed section."
                )
            sweep_profile_sketch, simplified_sweep_profile = _profile_sketch(
                sweep_profile_polygon,
                name="CADView Sweep Profile",
                tolerance=max(tolerance * 0.25, 1e-8),
            )
            sweep_profile_sketch["plane"] = "Top Plane"
            path_points = list(sweep_analysis["path_points"])
            path_length = float(LineString(path_points).length)
            features = [
                {
                    "id": "base-extrude-1",
                    "name": "CADView Outer Extrude",
                    "type": "extrude",
                    "depth": depth,
                    "start_offset": 0.0,
                    "end_condition": "midplane",
                    "role": "base",
                    "sketch": transformed_side_sketch,
                },
                {
                    "id": "perimeter-sweep-cut-1",
                    "name": "CADView Perimeter Sweep Cut",
                    "type": "sweep_cut",
                    "depth": float(sweep_analysis["maximum_depth"]),
                    "start_offset": 0.0,
                    "role": "perimeter_groove_sweep",
                    "profile": sweep_profile_sketch,
                    "path": {
                        "name": "CADView Sweep Path",
                        "plane": "Front Plane",
                        "kind": "polyline",
                        "points": path_points,
                        "closed": False,
                    },
                },
            ]
            reconstructed_volume = max(
                side_area * depth
                - path_length * float(simplified_sweep_profile.area),
                0.0,
            )
            strategy = "sweep_cut_reconstruction"
            representation = "native_sweep_cut"
            cut_area = float(simplified_sweep_profile.area)
        else:
            groove_region = simplified_side_polygon.difference(core_polygon)
            if groove_region.is_empty or groove_region.area <= 1e-10:
                raise ParametricReconstructionError(
                    "Detected a groove, but could not build a closed cut region."
                )
            if groove_region.geom_type == "MultiPolygon":
                groove_region = max(
                    groove_region.geoms, key=lambda item: item.area
                )
            groove_sketch, groove_polygon = _profile_sketch(
                groove_region,
                name="CADView Perimeter Groove Cut",
                tolerance=tolerance,
            )
            features = [
                {
                    "id": "base-extrude-1",
                    "name": "CADView Outer Extrude",
                    "type": "extrude",
                    "depth": depth,
                    "start_offset": 0.0,
                    "role": "base",
                    "sketch": side_sketch,
                },
                {
                    "id": "perimeter-groove-cut-1",
                    "name": "CADView Perimeter Groove Cut",
                    "type": "cut",
                    "depth": groove_width,
                    "start_offset": flange_depth,
                    "role": "perimeter_groove_cut",
                    "sketch": groove_sketch,
                },
            ]
            reconstructed_volume = (
                side_area * 2.0 * flange_depth + profile_area * groove_width
            )
            strategy = "multi_section_perimeter_groove"
            representation = "outer_extrude_plus_native_cut"
            cut_area = float(groove_polygon.area)

        candidate: dict[str, object] = {
            "id": "perimeter-groove-1",
            "type": "perimeter_groove",
            "classification": (
                "constant_profile_sweep"
                if sweep_selected
                else "variable_profile_sweep"
            ),
            "path": {
                "kind": (
                    "open_polyline"
                    if sweep_selected and sweep_analysis is not None
                    else "closed_polyline"
                ),
                "points": (
                    list(sweep_analysis["path_points"])
                    if sweep_selected and sweep_analysis is not None
                    else _coordinates(center_polygon.exterior.coords)
                ),
                "length": (
                    float(LineString(sweep_analysis["path_points"]).length)
                    if sweep_selected and sweep_analysis is not None
                    else float(center_polygon.exterior.length)
                ),
            },
            "section": {
                "axial_width": groove_width,
                "average_radial_depth": float(average_radial_depth),
                "maximum_radial_depth": (
                    float(sweep_analysis["maximum_depth"])
                    if sweep_selected and sweep_analysis is not None
                    else float(
                        center_polygon.exterior.hausdorff_distance(
                            side_polygon.exterior
                        )
                    )
                ),
            },
            "confidence": float(
                np.clip(
                    1.0
                    - side_symmetry_error
                    - center_outside_side_fraction,
                    0.0,
                    1.0,
                )
            ),
            "solidworks_representation": representation,
            "cut_area": cut_area,
        }
        if sweep_analysis is not None:
            candidate["intent_analysis"] = {
                key: value
                for key, value in sweep_analysis.items()
                if key
                not in {
                    "path_points",
                    "profile_points",
                    "profile_depth_samples",
                    "axial_samples",
                    "rotation_radians",
                    "translation_y",
                }
            }
        sweep_candidates.append(candidate)
    else:
        features = [
            {
                "id": "base-extrude-1",
                "name": "CADView Core Extrude",
                "type": "extrude",
                "depth": depth,
                "start_offset": 0.0,
                "role": "base",
                "sketch": core_sketch,
            }
        ]
        components = [(core_polygon, depth, 0.0)]
        reconstructed_volume = profile_area * depth
        strategy = "prismatic_extrusion"

    source_volume = abs(float(mesh.volume)) if mesh.is_watertight else None
    volume_error_percent = (
        abs(reconstructed_volume - source_volume) / max(source_volume, 1e-12) * 100
        if source_volume
        else None
    )
    confidence = max(0.0, 1.0 - min(thinness_ratio, 1.0))
    if volume_error_percent is not None:
        confidence *= max(0.0, 1.0 - min(volume_error_percent / 100.0, 1.0))
    if groove_detected:
        confidence *= max(0.0, 1.0 - min(side_symmetry_error, 1.0))

    deviation = _source_to_cad_deviation(
        mesh,
        center=center,
        axes=axes,
        extrusion_index=extrusion_index,
        axial_low=axial_low,
        components=components,
    )
    curvature_evidence = _curvature_segmentation_evidence(
        mesh,
        center=center,
        normal=normal,
        plane_basis=plane_basis,
        axial_low=axial_low,
        depth=depth,
    )

    warnings: list[str] = []
    if thinness_ratio > 0.35:
        warnings.append(
            "The mesh is not strongly prismatic; review multi-section features "
            "and deviation before using the model for manufacturing."
        )
    if volume_error_percent is not None and volume_error_percent > 5.0:
        warnings.append(
            f"Recovered feature volume differs from the mesh by "
            f"{volume_error_percent:.2f}%; review the recipe."
        )
    if groove_detected:
        if sweep_selected:
            warnings.append(
                "Orthogonal sections consistently match one groove profile, "
                "so the sweep hypothesis beat the stacked-cut hypothesis. "
                "SolidWorks will build a native Sweep-Cut."
            )
        else:
            warnings.append(
                "A perimeter groove was detected, but its orthogonal sections "
                "did not pass the constant-profile sweep gate. SolidWorks uses "
                "an editable outer extrude plus a native depth cut."
            )
    else:
        warnings.append(
            "No symmetric depth-varying perimeter groove passed the automatic "
            "segmentation thresholds."
        )

    return {
        "schema_version": "3.0",
        "strategy": strategy,
        "unit": unit,
        "confidence": float(confidence),
        "source": {
            "face_count": int(len(mesh.faces)),
            "watertight": bool(mesh.is_watertight),
            "extents": [float(value) for value in mesh.extents],
        },
        "features": features,
        "diagnostics": {
            "pca_spans": [float(value) for value in spans],
            "extrusion_axis_index": extrusion_index,
            "extrusion_axis_world": [float(value) for value in normal],
            "thinness_ratio": float(thinness_ratio),
            "profile_area": profile_area,
            "side_profile_area": side_area,
            "section_variation_fraction": float(variation_fraction),
            "side_symmetry_error": float(side_symmetry_error),
            "groove_detected": groove_detected,
            "groove_width": float(groove_width),
            "flange_depth": float(flange_depth),
            "section_samples": [
                {
                    "fraction": fraction,
                    "area": float(polygon.area),
                    "difference_from_center": _relative_profile_difference(
                        polygon, center_polygon
                    ),
                }
                for fraction, polygon in sections
            ],
            "sweep_candidates": sweep_candidates,
            "feature_intent": {
                "selected": (
                    "sweep_cut"
                    if sweep_selected
                    else "stacked_cut" if groove_detected else "extrude"
                ),
                "orthogonal_section_analysis": sweep_analysis,
            },
            "curvature_segmentation": curvature_evidence,
            "deviation": deviation,
            "reconstructed_volume": reconstructed_volume,
            "source_volume": source_volume,
            "volume_error_percent": volume_error_percent,
            "canonical_frame": {
                "center_world": [float(value) for value in center],
                "plane_basis_world": np.asarray(plane_basis).tolist(),
                "axial_low": axial_low,
                "axial_high": axial_high,
            },
        },
        "warnings": warnings,
    }


def solidworks_available() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"SldWorks.Application"):
            return True
    except OSError:
        return False


def build_solidworks_part(
    recipe: dict[str, Any],
    output_path: Path,
    *,
    visible: bool = False,
) -> None:
    """
    Execute a recipe through the installed SolidWorks COM API.

    The resulting SLDPRT contains native Sketch and Boss-Extrude history items.
    SolidWorks must be installed and licensed on this Windows machine.
    """
    if not solidworks_available():
        raise ParametricReconstructionError(
            "SolidWorks is not installed or its COM API is not registered."
        )

    bridge_dir = Path(__file__).resolve().parent / "solidworks_bridge"
    project_path = bridge_dir / "CadView.SolidWorksBridge.csproj"
    bridge_dll = (
        bridge_dir
        / "bin"
        / "Release"
        / "net9.0-windows"
        / "CadView.SolidWorksBridge.dll"
    )
    dotnet = shutil.which("dotnet")
    if dotnet is None or not project_path.exists():
        raise ParametricReconstructionError(
            "SolidWorks export requires the .NET 9 runtime and CAD-View bridge."
        )

    features = recipe.get("features", [])
    allowed = {"extrude", "cut", "sweep_cut"}
    if not features or any(feature.get("type") not in allowed for feature in features):
        raise ParametricReconstructionError(
            "The SolidWorks builder requires native extrude/cut/sweep features."
        )
    if recipe.get("unit") not in UNIT_TO_METERS:
        raise ParametricReconstructionError(
            f"Unsupported recipe unit: {recipe.get('unit')}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not bridge_dll.exists():
        build = subprocess.run(
            [dotnet, "build", str(project_path), "-c", "Release"],
            cwd=bridge_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if build.returncode != 0:
            raise ParametricReconstructionError(
                "Could not compile the SolidWorks bridge: "
                f"{build.stderr.strip() or build.stdout.strip()}"
            )

    recipe_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="cad-view-recipe-",
            dir=output_path.parent,
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(recipe, handle)
            recipe_file = Path(handle.name)

        command = [
            dotnet,
            str(bridge_dll),
            str(recipe_file.resolve()),
            str(output_path.resolve()),
        ]
        if visible:
            command.append("--visible")
        result = subprocess.run(
            command,
            cwd=bridge_dir,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0 or not output_path.exists():
            detail = result.stderr.strip() or result.stdout.strip()
            try:
                message = json.loads(detail).get("error", detail)
            except json.JSONDecodeError:
                message = detail
            raise ParametricReconstructionError(
                f"SolidWorks feature-tree build failed: {message}"
            )
    except subprocess.TimeoutExpired as exc:
        raise ParametricReconstructionError(
            "SolidWorks did not finish the feature-tree build within 3 minutes."
        ) from exc
    finally:
        if recipe_file is not None:
            recipe_file.unlink(missing_ok=True)


def write_solidworks_builder_script(
    recipe: dict[str, Any],
    output_path: Path,
) -> None:
    """Write an interactive VBScript that builds native SolidWorks features."""
    features = recipe.get("features", [])
    allowed = {"extrude", "cut", "sweep_cut"}
    if not features or any(feature.get("type") not in allowed for feature in features):
        raise ParametricReconstructionError(
            "The SolidWorks script requires native extrude/cut/sweep features."
        )
    unit = recipe.get("unit")
    if unit not in UNIT_TO_METERS:
        raise ParametricReconstructionError(f"Unsupported recipe unit: {unit}")

    scale = UNIT_TO_METERS[unit]
    lines: list[str] = [
        "Option Explicit",
        "Dim swApp, model, partDoc, planeFeature, sketchManager, segment, feature",
        "Dim template, scriptFolder, outputFile, errors, warnings, savedStatus",
        "Dim autoRelationsOriginal, selected, segmentIndex, createdCount, featureIndex",
        "Dim logFile, fso, stamp, sketchIndex, candidateFeature, splinePoints",
        "On Error Resume Next",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        'Set logFile = fso.CreateTextFile(fso.GetParentFolderName(WScript.ScriptFullName) & "\\CADView-builder-log.txt", True)',
        "On Error GoTo 0",
        'If logFile Is Nothing Then Err.Raise vbObjectError + 9, , "Could not create CADView-builder-log.txt"',
        'logFile.WriteLine "CAD-View SolidWorks builder log"',
        "On Error Resume Next",
        "Set swApp = Nothing",
        'Set swApp = GetObject(, "SldWorks.Application")',
        "On Error GoTo 0",
        "If swApp Is Nothing Then",
        '  Set swApp = CreateObject("SldWorks.Application")',
        '  logFile.WriteLine "sw_connect=CreateObject"',
        "Else",
        '  logFile.WriteLine "sw_connect=GetObject"',
        "End If",
        "swApp.Visible = True",
        "swApp.UserControl = True",
        # swDocPART = 1
        "swApp.DocumentVisible True, 1",
        # swSketchAutomaticRelations = 53
        "autoRelationsOriginal = swApp.GetUserPreferenceToggle(53)",
        "swApp.SetUserPreferenceToggle 53, False",
        "template = swApp.GetUserPreferenceStringValue(8)",
        'If Len(template) = 0 Then Err.Raise vbObjectError + 1, , "No default SolidWorks part template is configured."',
        'logFile.WriteLine "template=" & template',
        "Set model = swApp.NewDocument(template, 0, 0, 0)",
        'If model Is Nothing Then Err.Raise vbObjectError + 2, , "SolidWorks could not create a part document."',
        "WScript.Sleep 800",
        "model.Visible = True",
        'logFile.WriteLine "doc_title=" & model.GetTitle()',
        "Set partDoc = model",
        "Set sketchManager = model.SketchManager",
    ]

    def add_polyline(
        points: list[list[float]], label: str, *, closed: bool = True
    ) -> None:
        minimum = 3 if closed else 2
        if len(points) < minimum:
            raise ParametricReconstructionError(
                f"{label} has fewer than {minimum} points."
            )
        lines.append(f'logFile.WriteLine "{label}_points={len(points)}"')
        segment_count = len(points) if closed else len(points) - 1
        for index in range(segment_count):
            start = points[index]
            end = points[(index + 1) % len(points)]
            values = [
                float(start[0]) * scale,
                float(start[1]) * scale,
                0.0,
                float(end[0]) * scale,
                float(end[1]) * scale,
                0.0,
            ]
            arguments = ", ".join(format(value, ".17g") for value in values)
            lines.extend(
                [
                    "segmentIndex = segmentIndex + 1",
                    f"Set segment = sketchManager.CreateLine({arguments})",
                    "If Not segment Is Nothing Then createdCount = createdCount + 1",
                ]
            )

    def emit_sketch(
        sketch: dict[str, Any],
        *,
        label: str,
        closed: bool = True,
    ) -> int:
        plane_name = str(sketch.get("plane", "Front Plane")).replace('"', '""')
        outer_points = list(sketch["outer_loop"]["points"])
        sketch_name = str(sketch.get("name", label)).replace('"', '""')
        safe_label = label.replace('"', '""')
        lines.extend(
            [
                f'logFile.WriteLine "sketch_start={safe_label}"',
                "model.ClearSelection2 True",
                "selected = False",
                f'Set planeFeature = partDoc.FeatureByName("{plane_name}")',
                "If Not planeFeature Is Nothing Then selected = planeFeature.Select2(False, 0)",
                (
                    "If Not selected Then selected = "
                    f'model.Extension.SelectByID2("{plane_name}", "PLANE", '
                    "0, 0, 0, False, 0, Nothing, 0)"
                ),
                (
                    "If Not selected Then Err.Raise vbObjectError + 3, , "
                    f'"Could not select {plane_name} for {safe_label}."'
                ),
                "sketchManager.InsertSketch True",
                "WScript.Sleep 200",
                "If sketchManager.ActiveSketch Is Nothing Then",
                "  model.InsertSketch2 True",
                "  WScript.Sleep 300",
                "End If",
                "Set segment = sketchManager.CreateLine(0, 0, 0, 0.01, 0, 0)",
                'logFile.WriteLine "probe_line=" & (Not segment Is Nothing)',
                "If segment Is Nothing And sketchManager.ActiveSketch Is Nothing Then",
                (
                    "  Err.Raise vbObjectError + 8, , "
                    f'"SolidWorks did not enter sketch mode for {safe_label}."'
                ),
                "End If",
                "If Not segment Is Nothing Then",
                "  segment.Select4 False, Nothing",
                "  model.EditDelete",
                "End If",
                "model.SetAddToDB True",
                "model.SetDisplayWhenAdded False",
                "sketchManager.AddToDB = True",
                "sketchManager.DisplayWhenAdded = False",
                "segmentIndex = 0",
                "createdCount = 0",
            ]
        )
        if sketch.get("curve") == "spline":
            coordinates: list[str] = []
            for point in outer_points:
                coordinates.extend(
                    (
                        format(float(point[0]) * scale, ".17g"),
                        format(float(point[1]) * scale, ".17g"),
                        "0",
                    )
                )
            lines.extend(
                [
                    f"splinePoints = Array({', '.join(coordinates)})",
                    "Set segment = sketchManager.CreateSpline2((splinePoints), True)",
                    (
                        "If segment Is Nothing Then "
                        f'Err.Raise vbObjectError + 14, , "Could not create {safe_label} spline."'
                    ),
                    "createdCount = createdCount + 1",
                    f'logFile.WriteLine "{safe_label}_spline_points={len(outer_points)}"',
                ]
            )
        else:
            add_polyline(outer_points, f"{safe_label}_outer", closed=closed)
        for inner_index, inner in enumerate(
            sketch.get("inner_loops", []), start=1
        ):
            if inner["kind"] == "circle":
                x, y = inner["center"]
                radius = float(inner["radius"]) * scale
                lines.extend(
                    [
                        (
                            "Set segment = sketchManager.CreateCircleByRadius("
                            f"{format(float(x) * scale, '.17g')}, "
                            f"{format(float(y) * scale, '.17g')}, 0, "
                            f"{format(radius, '.17g')})"
                        ),
                        "If Not segment Is Nothing Then createdCount = createdCount + 1",
                        (
                            f'logFile.WriteLine "{safe_label}_'
                            f'inner_circle_{inner_index}=attempted"'
                        ),
                    ]
                )
            else:
                add_polyline(
                    list(inner["points"]),
                    f"{safe_label}_inner_{inner_index}",
                )
        lines.extend(
            [
                'logFile.WriteLine "segments_attempted=" & segmentIndex',
                'logFile.WriteLine "segments_non_nothing=" & createdCount',
                "model.SetAddToDB False",
                "model.SetDisplayWhenAdded True",
                "sketchManager.AddToDB = False",
                "sketchManager.DisplayWhenAdded = True",
                "model.ViewZoomtofit2",
                "sketchManager.InsertSketch True",
                "Set planeFeature = Nothing",
                "For sketchIndex = 1 To 100",
                "Set candidateFeature = Nothing",
                "On Error Resume Next",
                '  Set candidateFeature = partDoc.FeatureByName("Sketch" & sketchIndex)',
                "On Error GoTo 0",
                "  If Not candidateFeature Is Nothing Then Set planeFeature = candidateFeature",
                "Next",
                (
                    "If planeFeature Is Nothing Then "
                    f'Err.Raise vbObjectError + 10, , "Could not find {safe_label}."'
                ),
                f'planeFeature.Name = "{sketch_name}"',
                f'logFile.WriteLine "sketch_ok={safe_label}"',
            ]
        )
        return max(3 if closed else 2, len(outer_points) // 2)

    for feature_index, feature in enumerate(features, start=1):
        feature_type = str(feature.get("type", "extrude"))
        feature_name = str(
            feature.get("name", f"CADView Feature {feature_index}")
        ).replace('"', '""')
        lines.extend(
            [
                f"featureIndex = {feature_index}",
                f'logFile.WriteLine "feature_start={feature_index}:{feature_name}"',
            ]
        )

        if feature_type == "sweep_cut":
            path = dict(feature["path"])
            path_sketch = {
                "name": path["name"],
                "plane": path.get("plane", "Front Plane"),
                "curve": "spline",
                "outer_loop": {
                    "kind": "polyline",
                    "points": path["points"],
                },
                "inner_loops": [],
            }
            emit_sketch(
                path_sketch,
                label=f"feature_{feature_index}_path",
                closed=bool(path.get("closed", False)),
            )
            emit_sketch(
                dict(feature["profile"]),
                label=f"feature_{feature_index}_profile",
                closed=True,
            )
            profile_name = str(feature["profile"]["name"]).replace('"', '""')
            path_name = str(path["name"]).replace('"', '""')
            lines.extend(
                [
                    "model.ClearSelection2 True",
                    (
                        "selected = model.Extension.SelectByID2("
                        f'"{profile_name}", "SKETCH", 0, 0, 0, '
                        "False, 1, Nothing, 0)"
                    ),
                    (
                        "If Not selected Then Err.Raise vbObjectError + 11, , "
                        '"Could not select sweep profile."'
                    ),
                    (
                        "selected = model.Extension.SelectByID2("
                        f'"{path_name}", "SKETCH", 0, 0, 0, '
                        "True, 4, Nothing, 0)"
                    ),
                    (
                        "If Not selected Then Err.Raise vbObjectError + 12, , "
                        '"Could not select sweep path."'
                    ),
                    (
                        "Set feature = model.FeatureManager.InsertCutSwept5("
                        "False, False, 0, True, True, 0, 0, False, "
                        "0, 0, 0, 0, True, True, 0, True, False, "
                        "True, False, False, 0, 0)"
                    ),
                    "If feature Is Nothing Then",
                    (
                        "  Err.Raise vbObjectError + 13, , "
                        '"SolidWorks rejected the recovered Sweep-Cut."'
                    ),
                    "End If",
                    f'feature.Name = "{feature_name}"',
                    "model.EditRebuild3",
                    f'logFile.WriteLine "feature_ok={feature_index}:sweep_cut"',
                ]
            )
            continue

        sketch = dict(feature["sketch"])
        expected_min = emit_sketch(
            sketch, label=f"feature_{feature_index}_profile", closed=True
        )
        depth = format(float(feature["depth"]) * scale, ".17g")
        start_offset_value = float(feature.get("start_offset", 0.0))
        start_offset = format(start_offset_value * scale, ".17g")
        start_condition = 3 if abs(start_offset_value) > 1e-12 else 0
        if feature_type == "cut":
            create_feature = (
                "Set feature = model.FeatureManager.FeatureCut3("
                f"True, False, False, 0, 0, {depth}, 0, "
                "False, False, False, False, 0, 0, False, False, "
                "False, False, False, True, True, True, True, False, "
                f"{start_condition}, {start_offset}, False)"
            )
        else:
            end_condition = 6 if feature.get("end_condition") == "midplane" else 0
            create_feature = (
                "Set feature = model.FeatureManager.FeatureExtrusion3("
                f"True, False, False, {end_condition}, 0, {depth}, 0, "
                "False, False, False, True, 0, 0, False, False, "
                "False, False, True, False, True, "
                f"{start_condition}, {start_offset}, False)"
            )
        lines.extend(
            [
                create_feature,
                "If feature Is Nothing Then",
                (
                    "  Err.Raise vbObjectError + 6, , "
                    f'"SolidWorks rejected feature {feature_index} after " & '
                    'segmentIndex & " line attempts (" & createdCount & '
                    f'" non-Nothing returns; expected about {expected_min})."'
                ),
                "End If",
                f'feature.Name = "{feature_name}"',
                "model.EditRebuild3",
                f'logFile.WriteLine "feature_ok={feature_index}"',
            ]
        )

    lines.extend(
        [
            "model.ForceRebuild3 True",
            'scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)',
            # Unique filename avoids Explorer/shell collisions with a previous
            # CADView-editable.SLDPRT that SolidWorks still has locked open.
            'stamp = Year(Now) & Right("0" & Month(Now), 2) & Right("0" & Day(Now), 2) & "-" & Right("0" & Hour(Now), 2) & Right("0" & Minute(Now), 2) & Right("0" & Second(Now), 2)',
            'outputFile = scriptFolder & "\\CADView-editable-" & stamp & ".SLDPRT"',
            "savedStatus = model.SaveAs3(outputFile, 0, 1)",
            'logFile.WriteLine "save_status=" & savedStatus',
            "If savedStatus <> 0 Or Not fso.FileExists(outputFile) Then",
            (
                '  Err.Raise vbObjectError + 7, , '
                '"SolidWorks SaveAs3 failed. Status: " & savedStatus'
            ),
            "End If",
            "swApp.SetUserPreferenceToggle 53, autoRelationsOriginal",
            'logFile.WriteLine "saved=" & outputFile',
            "logFile.Close",
            (
                'MsgBox "Editable SolidWorks part is open in SolidWorks with '
                f'{len(features)} native features." & vbCrLf & vbCrLf & '
                '"Saved as:" & vbCrLf & outputFile & vbCrLf & vbCrLf & '
                '"Do not double-click the file from Explorer while SolidWorks '
                'still has it open.", vbInformation, "CAD-View"'
            ),
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Windows Script Host's legacy VBScript parser rejects a UTF-8 BOM as an
    # invalid first character. Generated source is intentionally ASCII-only.
    # Write bytes so Windows text-mode newline translation cannot turn CRLF
    # into CR+CRLF.
    output_path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))


def write_recipe(recipe: dict[str, object], output_path: Path) -> None:
    output_path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
