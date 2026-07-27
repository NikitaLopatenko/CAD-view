from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cadquery as cq
import numpy as np
import trimesh

PrimitiveType = Literal["box", "cylinder"]


@dataclass
class PrimitiveCandidate:
    primitive_type: PrimitiveType
    parameters: dict[str, object]
    transform: np.ndarray
    rms_deviation: float
    max_deviation: float
    normalized_rms: float

    def report(self) -> dict[str, object]:
        return {
            "primitive_type": self.primitive_type,
            "parameters": self.parameters,
            "rms_deviation": self.rms_deviation,
            "max_deviation": self.max_deviation,
            "normalized_rms": self.normalized_rms,
        }


def _surface_samples(mesh: trimesh.Trimesh) -> np.ndarray:
    return np.vstack(
        (
            np.asarray(mesh.vertices, dtype=np.float64),
            np.asarray(mesh.triangles_center, dtype=np.float64),
        )
    )


def _right_handed_axes(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    origin = samples.mean(axis=0)
    covariance = np.cov((samples - origin).T)
    _, axes = np.linalg.eigh(covariance)
    left, _, right = np.linalg.svd(axes)
    axes = left @ right
    if np.linalg.det(axes) < 0:
        axes[:, 0] *= -1
    return origin, axes


def _normalization_length(mesh: trimesh.Trimesh) -> float:
    diagonal = float(np.linalg.norm(mesh.extents))
    return max(diagonal, np.finfo(np.float64).eps)


def fit_box(mesh: trimesh.Trimesh) -> PrimitiveCandidate:
    samples = _surface_samples(mesh)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    origin, axes = _right_handed_axes(samples)
    vertex_local = (vertices - origin) @ axes
    local_min = vertex_local.min(axis=0)
    local_max = vertex_local.max(axis=0)
    local = (samples - origin) @ axes
    local_center = (local_min + local_max) / 2.0
    dimensions = local_max - local_min
    centered = local - local_center
    half = dimensions / 2.0

    outside = np.maximum(np.abs(centered) - half, 0.0)
    outside_distance = np.linalg.norm(outside, axis=1)
    inside_distance = np.min(np.maximum(half - np.abs(centered), 0.0), axis=1)
    is_outside = np.any(outside > 1e-12, axis=1)
    deviations = np.where(is_outside, outside_distance, inside_distance)

    world_center = origin + axes @ local_center
    transform = np.eye(4)
    transform[:3, :3] = axes
    transform[:3, 3] = world_center
    rms = float(np.sqrt(np.mean(np.square(deviations))))
    return PrimitiveCandidate(
        primitive_type="box",
        parameters={
            "dimensions": [float(value) for value in dimensions],
            "center": [float(value) for value in world_center],
            "axes": axes.tolist(),
        },
        transform=transform,
        rms_deviation=rms,
        max_deviation=float(np.max(deviations)),
        normalized_rms=rms / _normalization_length(mesh),
    )


def _basis_for_axis(axis: np.ndarray) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    reference = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(reference, axis))) > 0.9:
        reference = np.array([0.0, 1.0, 0.0])
    x_axis = np.cross(reference, axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(axis, x_axis)
    return np.column_stack((x_axis, y_axis, axis))


def _fit_cylinder_for_axis(
    mesh: trimesh.Trimesh, axis: np.ndarray
) -> PrimitiveCandidate:
    samples = _surface_samples(mesh)
    mean = samples.mean(axis=0)
    basis = _basis_for_axis(axis)
    coordinates = (samples - mean) @ basis
    center_u = float(np.median(coordinates[:, 0]))
    center_v = float(np.median(coordinates[:, 1]))
    radial_from_center = np.linalg.norm(
        coordinates[:, :2] - np.array([center_u, center_v]), axis=1
    )
    radius = float(np.percentile(radial_from_center, 95))

    axial_min = float(coordinates[:, 2].min())
    axial_max = float(coordinates[:, 2].max())
    axial_center = (axial_min + axial_max) / 2.0
    height = axial_max - axial_min
    local_center = np.array([center_u, center_v, axial_center])
    centered = coordinates - local_center
    radial = np.linalg.norm(centered[:, :2], axis=1)
    axial = np.abs(centered[:, 2])
    half_height = height / 2.0

    side_distance = np.sqrt(
        np.square(radial - radius)
        + np.square(np.maximum(axial - half_height, 0.0))
    )
    cap_distance = np.sqrt(
        np.square(np.maximum(radial - radius, 0.0))
        + np.square(axial - half_height)
    )
    deviations = np.minimum(side_distance, cap_distance)

    world_center = mean + basis @ local_center
    transform = np.eye(4)
    transform[:3, :3] = basis
    transform[:3, 3] = world_center
    rms = float(np.sqrt(np.mean(np.square(deviations))))
    return PrimitiveCandidate(
        primitive_type="cylinder",
        parameters={
            "radius": radius,
            "height": float(height),
            "center": [float(value) for value in world_center],
            "axis": [float(value) for value in basis[:, 2]],
        },
        transform=transform,
        rms_deviation=rms,
        max_deviation=float(np.max(deviations)),
        normalized_rms=rms / _normalization_length(mesh),
    )


def fit_cylinder(mesh: trimesh.Trimesh) -> PrimitiveCandidate:
    samples = _surface_samples(mesh)
    _, axes = _right_handed_axes(samples)
    candidates = [
        _fit_cylinder_for_axis(mesh, axes[:, index]) for index in range(3)
    ]
    return min(candidates, key=lambda candidate: candidate.rms_deviation)


def analyze_primitives(mesh: trimesh.Trimesh) -> list[PrimitiveCandidate]:
    return sorted(
        [fit_box(mesh), fit_cylinder(mesh)],
        key=lambda candidate: candidate.normalized_rms,
    )


def export_step(candidate: PrimitiveCandidate, output_path: Path) -> None:
    if candidate.primitive_type == "box":
        dimensions = candidate.parameters["dimensions"]
        center = candidate.parameters["center"]
        axes = candidate.parameters["axes"]
        assert isinstance(dimensions, list)
        assert isinstance(center, list)
        assert isinstance(axes, list)
        plane = cq.Plane(
            origin=cq.Vector(*center),
            xDir=cq.Vector(*[axes[row][0] for row in range(3)]),
            normal=cq.Vector(*[axes[row][2] for row in range(3)]),
        )
        shape = cq.Workplane(plane).box(*dimensions).val()
    else:
        radius = float(candidate.parameters["radius"])
        height = float(candidate.parameters["height"])
        center = np.asarray(candidate.parameters["center"], dtype=np.float64)
        axis = np.asarray(candidate.parameters["axis"], dtype=np.float64)
        x_axis = candidate.transform[:3, 0]
        start = center - axis * (height / 2.0)
        plane = cq.Plane(
            origin=cq.Vector(*start),
            xDir=cq.Vector(*x_axis),
            normal=cq.Vector(*axis),
        )
        shape = (
            cq.Workplane(plane)
            .circle(radius)
            .extrude(height)
            .val()
        )

    cq.exporters.export(shape, str(output_path))


def _count_subshapes(shape: object, shape_type: object) -> int:
    from OCP.TopExp import TopExp_Explorer

    count = 0
    explorer = TopExp_Explorer(shape, shape_type)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def export_mesh_shape_step(
    mesh: trimesh.Trimesh,
    output_path: Path,
    *,
    max_faces: int = 80_000,
) -> dict[str, object]:
    """
    Export the mesh silhouette as a faceted STEP body (shape-preserving).

    This is NOT an analytic feature tree. SolidWorks imports it as an edited
    dumb solid that matches the mesh, unlike single box/cylinder approximation.
    """
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakePolygon,
        BRepBuilderAPI_MakeSolid,
        BRepBuilderAPI_Sewing,
    )
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt

    working = mesh.copy()
    if not isinstance(working, trimesh.Trimesh):
        raise ValueError("Mesh solid STEP export requires a triangle mesh.")
    working.merge_vertices()
    working.remove_unreferenced_vertices()
    if working.faces is None or len(working.faces) == 0:
        raise ValueError("Mesh has no faces to export.")

    face_count_before = int(len(working.faces))
    if face_count_before > max_faces:
        try:
            simplified = working.simplify_quadric_decimation(max_faces)
        except Exception as exc:  # noqa: BLE001 - optional dependency path
            raise ValueError(
                f"Mesh has {face_count_before} faces (limit {max_faces}). "
                "Install fast_simplification or reduce the mesh before STEP export."
            ) from exc
        if simplified is None or len(simplified.faces) == 0:
            raise ValueError("Mesh decimation failed before STEP export.")
        working = simplified
        working.remove_unreferenced_vertices()

    sewer = BRepBuilderAPI_Sewing(1e-6)
    vertices = np.asarray(working.vertices, dtype=np.float64)
    for triangle in np.asarray(working.faces, dtype=np.int64):
        polygon = BRepBuilderAPI_MakePolygon()
        for index in triangle:
            x, y, z = vertices[int(index)]
            polygon.Add(gp_Pnt(float(x), float(y), float(z)))
        polygon.Close()
        if not polygon.IsDone():
            continue
        face = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
        sewer.Add(face)
    sewer.Perform()
    sewed = sewer.SewedShape()

    shell_explorer = TopExp_Explorer(sewed, TopAbs_SHELL)
    if not shell_explorer.More():
        raise ValueError(
            "Could not sew mesh faces into a closed shell. "
            "Repair topology (watertight) and try again."
        )

    shell = TopoDS.Shell_s(shell_explorer.Current())
    solid_maker = BRepBuilderAPI_MakeSolid(shell)
    if not solid_maker.IsDone():
        raise ValueError(
            "Sewed shell could not be converted to a solid. "
            "The mesh may not be watertight."
        )
    solid = solid_maker.Solid()
    cq.exporters.export(cq.Shape.cast(solid), str(output_path))
    return {
        "face_count_source": face_count_before,
        "face_count_exported": int(len(working.faces)),
        "shell_faces": _count_subshapes(solid, TopAbs_FACE),
        "decimated": face_count_before > max_faces,
    }
