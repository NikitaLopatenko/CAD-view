"""
Geometry-grounded surface patch analysis for mesh-to-CAD reconstruction.

Point2CAD and Point2Cyl both recover stable geometric proxies before choosing
CAD operations. This module follows that principle without requiring a trained
segmenter: smooth connected faces are region-grown, then each region is tested
against plane and cylinder models. The result is evidence for feature
hypotheses, not a claim that the original design history has been recovered.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import trimesh

DEFAULT_SMOOTH_ANGLE_DEGREES = 15.0
DEFAULT_MINIMUM_AREA_FRACTION = 0.001
PLANE_RMS_RATIO = 0.002
CYLINDER_RMS_RATIO = 0.02
MINIMUM_CURVATURE_ANGLE_DEGREES = 3.0


def _face_regions(mesh: trimesh.Trimesh, smooth_angle: float) -> list[np.ndarray]:
    face_count = len(mesh.faces)
    parent = np.arange(face_count, dtype=np.int64)

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = int(parent[index])
        return index

    adjacency = np.asarray(mesh.face_adjacency, dtype=np.int64)
    angles = np.asarray(mesh.face_adjacency_angles, dtype=np.float64)
    for (left, right), angle in zip(adjacency, angles):
        if float(angle) > smooth_angle:
            continue
        left_root, right_root = root(int(left)), root(int(right))
        if left_root != right_root:
            parent[right_root] = left_root

    grouped: dict[int, list[int]] = {}
    for face in range(face_count):
        grouped.setdefault(root(face), []).append(face)
    return [
        np.asarray(faces, dtype=np.int64)
        for faces in sorted(grouped.values(), key=len, reverse=True)
    ]


def _selected_face_components(
    mesh: trimesh.Trimesh, selected: np.ndarray
) -> list[np.ndarray]:
    parent = np.arange(len(mesh.faces), dtype=np.int64)

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = int(parent[index])
        return index

    for left, right in np.asarray(mesh.face_adjacency, dtype=np.int64):
        if not selected[left] or not selected[right]:
            continue
        left_root, right_root = root(int(left)), root(int(right))
        if left_root != right_root:
            parent[right_root] = left_root
    grouped: dict[int, list[int]] = {}
    for face in np.flatnonzero(selected):
        grouped.setdefault(root(int(face)), []).append(int(face))
    return [
        np.asarray(faces, dtype=np.int64)
        for faces in sorted(grouped.values(), key=len, reverse=True)
    ]


def _curvature_bands(
    mesh: trimesh.Trimesh,
    *,
    minimum_area_fraction: float,
) -> dict[str, Any]:
    """
    Locate connected high-dihedral bands that can seed fillet/sweep hypotheses.

    This is a discrete curvature proxy rather than a fitted feature. Reporting
    bounds and dominant angle makes curved detail visible even when smooth
    region growing joins an entire scanned shell into one freeform patch.
    """
    adjacency = np.asarray(mesh.face_adjacency, dtype=np.int64)
    angles = np.asarray(mesh.face_adjacency_angles, dtype=np.float64)
    face_curvature = np.zeros(len(mesh.faces), dtype=np.float64)
    for (left, right), angle in zip(adjacency, angles):
        face_curvature[left] = max(face_curvature[left], float(angle))
        face_curvature[right] = max(face_curvature[right], float(angle))
    positive = face_curvature[face_curvature > 0.0]
    if len(positive) == 0:
        return {"threshold_degrees": None, "bands": []}
    threshold = max(
        float(np.radians(MINIMUM_CURVATURE_ANGLE_DEGREES)),
        float(np.percentile(positive, 85)),
    )
    selected = face_curvature >= threshold
    total_area = max(float(mesh.area), np.finfo(float).eps)
    centers = np.asarray(mesh.triangles_center, dtype=np.float64)
    areas = np.asarray(mesh.area_faces, dtype=np.float64)
    bands: list[dict[str, Any]] = []
    for index, faces in enumerate(_selected_face_components(mesh, selected)):
        area = float(np.sum(areas[faces]))
        if area / total_area < minimum_area_fraction:
            continue
        vertices = np.asarray(mesh.vertices)[np.unique(mesh.faces[faces])]
        bands.append(
            {
                "id": f"curvature-band-{index + 1}",
                "face_count": int(len(faces)),
                "area_fraction": area / total_area,
                "centroid": [
                    float(value)
                    for value in np.average(
                        centers[faces], axis=0, weights=areas[faces]
                    )
                ],
                "bounds": np.asarray(
                    [vertices.min(axis=0), vertices.max(axis=0)]
                ).tolist(),
                "mean_angle_degrees": float(
                    np.degrees(np.average(face_curvature[faces], weights=areas[faces]))
                ),
                "maximum_angle_degrees": float(
                    np.degrees(np.max(face_curvature[faces]))
                ),
            }
        )
    bands.sort(key=lambda band: float(band["area_fraction"]), reverse=True)
    return {
        "threshold_degrees": float(np.degrees(threshold)),
        "bands": bands[:20],
    }


def _weighted_plane_fit(
    points: np.ndarray, weights: np.ndarray, scale: float
) -> dict[str, Any]:
    origin = np.average(points, axis=0, weights=weights)
    centered = points - origin
    covariance = (centered * weights[:, None]).T @ centered / max(
        float(np.sum(weights)), np.finfo(float).eps
    )
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    normal = eigenvectors[:, int(np.argmin(eigenvalues))]
    distances = np.abs(centered @ normal)
    rms = float(np.sqrt(np.average(np.square(distances), weights=weights)))
    return {
        "origin": [float(value) for value in origin],
        "normal": [float(value) for value in normal],
        "rms": rms,
        "normalized_rms": rms / scale,
    }


def _orthogonal_basis(axis: np.ndarray) -> np.ndarray:
    axis = axis / max(float(np.linalg.norm(axis)), np.finfo(float).eps)
    reference = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(reference, axis))) > 0.9:
        reference = np.array([0.0, 1.0, 0.0])
    first = np.cross(axis, reference)
    first /= max(float(np.linalg.norm(first)), np.finfo(float).eps)
    second = np.cross(axis, first)
    return np.column_stack((first, second, axis))


def _circle_fit(points: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, float]:
    x, y = points[:, 0], points[:, 1]
    matrix = np.column_stack((2.0 * x, 2.0 * y, np.ones(len(points))))
    rhs = np.square(x) + np.square(y)
    weighted_matrix = matrix * np.sqrt(weights)[:, None]
    weighted_rhs = rhs * np.sqrt(weights)
    center_x, center_y, constant = np.linalg.lstsq(
        weighted_matrix, weighted_rhs, rcond=None
    )[0]
    radius_squared = constant + center_x**2 + center_y**2
    return (
        np.array([center_x, center_y], dtype=np.float64),
        float(np.sqrt(max(radius_squared, 0.0))),
    )


def _weighted_cylinder_fit(
    points: np.ndarray,
    normals: np.ndarray,
    weights: np.ndarray,
    scale: float,
    extent_points: np.ndarray,
) -> dict[str, Any]:
    # Barrel normals span the plane perpendicular to a cylinder's axis, so the
    # least energetic eigenvector of their covariance estimates that axis.
    normal_covariance = (normals * weights[:, None]).T @ normals / max(
        float(np.sum(weights)), np.finfo(float).eps
    )
    _, eigenvectors = np.linalg.eigh(normal_covariance)
    axis = eigenvectors[:, 0]
    basis = _orthogonal_basis(axis)
    mean = np.average(points, axis=0, weights=weights)
    local = (points - mean) @ basis
    center_2d, radius = _circle_fit(local[:, :2], weights)
    radial = np.linalg.norm(local[:, :2] - center_2d, axis=1)
    radial_error = radial - radius
    rms = float(
        np.sqrt(np.average(np.square(radial_error), weights=weights))
    )
    extent_local = (extent_points - mean) @ basis
    axial_low = float(np.min(extent_local[:, 2]))
    axial_high = float(np.max(extent_local[:, 2]))
    center_local = np.array(
        [center_2d[0], center_2d[1], (axial_low + axial_high) * 0.5]
    )
    center_world = mean + basis @ center_local
    axial_normal_fraction = float(
        np.average(np.abs(normals @ axis), weights=weights)
    )
    return {
        "axis": [float(value) for value in axis],
        "center": [float(value) for value in center_world],
        "radius": radius,
        "height": axial_high - axial_low,
        "rms": rms,
        "normalized_rms": rms / scale,
        "axial_normal_fraction": axial_normal_fraction,
    }


def _region_boundary_count(
    mesh: trimesh.Trimesh, faces: np.ndarray
) -> int:
    selected = np.zeros(len(mesh.faces), dtype=bool)
    selected[faces] = True
    adjacency = np.asarray(mesh.face_adjacency, dtype=np.int64)
    crossings = selected[adjacency[:, 0]] != selected[adjacency[:, 1]]
    return int(np.count_nonzero(crossings))


def analyze_surface_patches(
    mesh: trimesh.Trimesh,
    *,
    smooth_angle_degrees: float = DEFAULT_SMOOTH_ANGLE_DEGREES,
    minimum_area_fraction: float = DEFAULT_MINIMUM_AREA_FRACTION,
) -> dict[str, Any]:
    """
    Segment a mesh into smooth patches and classify plane/cylinder/freeform.

    Classification is deliberately conservative. A patch that does not pass an
    explicit geometric residual gate remains ``freeform`` and may seed a sweep,
    loft, or finishing-feature hypothesis later.
    """
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ValueError("Surface analysis requires a non-empty triangle mesh.")
    scale = max(float(np.linalg.norm(mesh.extents)), np.finfo(float).eps)
    total_area = max(float(mesh.area), np.finfo(float).eps)
    smooth_angle = float(np.radians(smooth_angle_degrees))
    centers = np.asarray(mesh.triangles_center, dtype=np.float64)
    normals = np.asarray(mesh.face_normals, dtype=np.float64)
    areas = np.asarray(mesh.area_faces, dtype=np.float64)

    patches: list[dict[str, Any]] = []
    ignored_area = 0.0
    for region_index, faces in enumerate(_face_regions(mesh, smooth_angle)):
        area = float(np.sum(areas[faces]))
        area_fraction = area / total_area
        if area_fraction < minimum_area_fraction:
            ignored_area += area
            continue
        points = centers[faces]
        weights = np.maximum(areas[faces], np.finfo(float).eps)
        vertices = np.asarray(mesh.vertices)[np.unique(mesh.faces[faces])]
        plane = _weighted_plane_fit(points, weights, scale)
        cylinder = _weighted_cylinder_fit(
            points, normals[faces], weights, scale, vertices
        )
        if float(plane["normalized_rms"]) <= PLANE_RMS_RATIO:
            surface_type = "plane"
            parameters = plane
        elif (
            float(cylinder["normalized_rms"]) <= CYLINDER_RMS_RATIO
            and float(cylinder["axial_normal_fraction"]) <= 0.15
        ):
            surface_type = "cylinder"
            parameters = cylinder
        else:
            surface_type = "freeform"
            parameters = {
                "plane_normalized_rms": plane["normalized_rms"],
                "cylinder_normalized_rms": cylinder["normalized_rms"],
            }

        mean_normal = np.average(normals[faces], axis=0, weights=weights)
        mean_normal /= max(float(np.linalg.norm(mean_normal)), np.finfo(float).eps)
        patches.append(
            {
                "id": f"surface-patch-{region_index + 1}",
                "surface_type": surface_type,
                "face_count": int(len(faces)),
                "area": area,
                "area_fraction": area_fraction,
                "centroid": [
                    float(value)
                    for value in np.average(points, axis=0, weights=weights)
                ],
                "bounds": np.asarray(
                    [vertices.min(axis=0), vertices.max(axis=0)]
                ).tolist(),
                "mean_normal": [float(value) for value in mean_normal],
                "boundary_adjacency_count": _region_boundary_count(mesh, faces),
                "fit": parameters,
            }
        )

    counts = {
        surface_type: sum(
            patch["surface_type"] == surface_type for patch in patches
        )
        for surface_type in ("plane", "cylinder", "freeform")
    }
    return {
        "smooth_angle_degrees": smooth_angle_degrees,
        "minimum_area_fraction": minimum_area_fraction,
        "patch_count": len(patches),
        "counts": counts,
        "covered_area_fraction": float(
            np.clip(1.0 - ignored_area / total_area, 0.0, 1.0)
        ),
        "curvature_analysis": _curvature_bands(
            mesh, minimum_area_fraction=minimum_area_fraction
        ),
        "patches": patches,
    }
