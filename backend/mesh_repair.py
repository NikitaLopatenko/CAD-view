from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh


class MeshRepairError(RuntimeError):
    pass


@dataclass(frozen=True)
class BoundaryFillResult:
    loops_found: int
    loops_filled: int
    faces_added: int


@dataclass(frozen=True)
class ProxyDiagnostics:
    method: str
    boundary_loops_filled: int
    voxel_resolution: int
    voxel_pitch: float
    closing_radius_voxels: int
    smoothing_iterations: int
    rms_deviation: float
    p95_deviation: float
    max_deviation: float
    normalized_rms_percent: float


def _directed_boundary_loops(mesh: trimesh.Trimesh) -> list[np.ndarray]:
    """Return consistently wound boundary cycles from an oriented triangle mesh."""
    faces = np.asarray(mesh.faces, dtype=np.int64)
    directed = np.vstack(
        (faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])
    )
    undirected = np.sort(directed, axis=1)
    _, inverse, counts = np.unique(
        undirected, axis=0, return_inverse=True, return_counts=True
    )
    boundary = directed[counts[inverse] == 1]
    if not len(boundary):
        return []

    outgoing: dict[int, int] = {}
    incoming: dict[int, int] = {}
    for start, stop in boundary:
        start_i, stop_i = int(start), int(stop)
        if start_i in outgoing or stop_i in incoming:
            # Branching boundaries are not simple holes and must not be guessed.
            continue
        outgoing[start_i] = stop_i
        incoming[stop_i] = start_i

    loops: list[np.ndarray] = []
    while outgoing:
        start = next(iter(outgoing))
        cycle = [start]
        current = start
        visited: set[int] = set()
        while current in outgoing and current not in visited:
            visited.add(current)
            following = outgoing.pop(current)
            incoming.pop(following, None)
            if following == start:
                if len(cycle) >= 3:
                    loops.append(np.asarray(cycle, dtype=np.int64))
                break
            cycle.append(following)
            current = following
    return loops


def boundary_edge_count(mesh: trimesh.Trimesh) -> int:
    edges = np.sort(np.asarray(mesh.edges, dtype=np.int64), axis=1)
    if not len(edges):
        return 0
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int(np.count_nonzero(counts == 1))


def non_manifold_edge_count(mesh: trimesh.Trimesh) -> int:
    edges = np.sort(np.asarray(mesh.edges, dtype=np.int64), axis=1)
    if not len(edges):
        return 0
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int(np.count_nonzero(counts > 2))


def fill_boundary_loops(mesh: trimesh.Trimesh) -> BoundaryFillResult:
    """
    Triangulate arbitrary simple boundary loops without moving observed vertices.

    The loop is projected to its least-squares plane and triangulated with
    Mapbox Earcut. New triangles are wound opposite the existing boundary.
    """
    import mapbox_earcut

    loops = _directed_boundary_loops(mesh)
    if not loops:
        return BoundaryFillResult(loops_found=0, loops_filled=0, faces_added=0)

    additions: list[np.ndarray] = []
    filled = 0
    for loop in loops:
        points = np.asarray(mesh.vertices[loop], dtype=np.float64)
        centered = points - points.mean(axis=0)
        try:
            _, _, basis = np.linalg.svd(centered, full_matrices=False)
        except np.linalg.LinAlgError:
            continue
        projected = np.ascontiguousarray(centered @ basis[:2].T, dtype=np.float64)
        rings = np.asarray([len(loop)], dtype=np.uint32)
        indices = np.asarray(
            mapbox_earcut.triangulate_float64(projected, rings), dtype=np.int64
        )
        if len(indices) < 3 or len(indices) % 3:
            continue
        triangles = loop[indices.reshape((-1, 3))]

        directed_boundary = {
            (int(left), int(right))
            for left, right in zip(loop, np.roll(loop, -1))
        }
        same = 0
        opposite = 0
        for triangle in triangles:
            for left, right in zip(triangle, np.roll(triangle, -1)):
                edge = (int(left), int(right))
                if edge in directed_boundary:
                    same += 1
                if (edge[1], edge[0]) in directed_boundary:
                    opposite += 1
        if same > opposite:
            triangles = triangles[:, [0, 2, 1]]
        additions.append(triangles)
        filled += 1

    if additions:
        mesh.faces = np.vstack((mesh.faces, *additions))
        mesh.remove_unreferenced_vertices()
        mesh.update_faces(mesh.unique_faces())
        trimesh.repair.fix_normals(mesh, multibody=False)

    faces_added = int(sum(len(value) for value in additions))
    return BoundaryFillResult(
        loops_found=len(loops), loops_filled=filled, faces_added=faces_added
    )


def _surface_deviation(
    source: trimesh.Trimesh, candidate: trimesh.Trimesh, count: int = 8_000
) -> tuple[float, float, float]:
    source_points, _ = trimesh.sample.sample_surface(source, count, seed=17)
    candidate_points, _ = trimesh.sample.sample_surface(candidate, count, seed=29)
    source_distance = trimesh.proximity.closest_point(candidate, source_points)[1]
    candidate_distance = trimesh.proximity.closest_point(source, candidate_points)[1]
    distances = np.concatenate((source_distance, candidate_distance))
    return (
        float(np.sqrt(np.mean(np.square(distances)))),
        float(np.quantile(distances, 0.95)),
        float(np.max(distances)),
    )


def create_watertight_proxy(
    source: trimesh.Trimesh,
    *,
    resolution: int = 160,
    closing_radius_voxels: int = 2,
    smoothing_iterations: int = 6,
) -> tuple[trimesh.Trimesh, ProxyDiagnostics]:
    """
    Build a separate, regularized watertight proxy for printing/CAD analysis.

    This is deliberately not called a repair of observed geometry: volumetric
    wrapping and closing infer a surface where the scan is defective.
    """
    try:
        from scipy.ndimage import binary_closing, binary_fill_holes
        from skimage.measure import marching_cubes
    except ImportError as exc:
        raise MeshRepairError(
            "Watertight proxy generation requires scipy and scikit-image."
        ) from exc

    resolution = max(64, min(int(resolution), 320))
    closing_radius_voxels = max(0, min(int(closing_radius_voxels), 8))
    smoothing_iterations = max(0, min(int(smoothing_iterations), 30))

    working = source.copy()
    working.remove_unreferenced_vertices()
    working.update_faces(working.unique_faces())
    trimesh.repair.fix_normals(working, multibody=False)
    fill_result = fill_boundary_loops(working)
    if not working.is_watertight:
        raise MeshRepairError(
            "The scan has branching or non-simple openings that need a user hint "
            "before volumetric wrapping."
        )

    longest = float(np.max(working.extents))
    if not np.isfinite(longest) or longest <= 0:
        raise MeshRepairError("The scan has invalid dimensions.")
    pitch = longest / float(resolution)

    voxels = working.voxelized(pitch, method="subdivide").fill()
    occupancy = np.asarray(voxels.matrix, dtype=bool)
    padding = closing_radius_voxels + 2
    occupancy = np.pad(occupancy, padding, constant_values=False)
    if closing_radius_voxels:
        coordinate = np.arange(
            -closing_radius_voxels, closing_radius_voxels + 1
        )
        xx, yy, zz = np.meshgrid(coordinate, coordinate, coordinate, indexing="ij")
        structuring_element = (
            xx * xx + yy * yy + zz * zz
            <= closing_radius_voxels * closing_radius_voxels
        )
        occupancy = binary_closing(
            occupancy, structure=structuring_element, border_value=0
        )
    occupancy = binary_fill_holes(occupancy)

    vertices, faces, _, _ = marching_cubes(
        occupancy.astype(np.float32),
        level=0.5,
        spacing=(pitch, pitch, pitch),
        allow_degenerate=False,
    )
    vertices += np.asarray(voxels.transform[:3, 3]) - padding * pitch
    proxy = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    components = proxy.split(only_watertight=False)
    if components:
        proxy = max(components, key=lambda component: float(abs(component.volume)))
    if smoothing_iterations:
        trimesh.smoothing.filter_taubin(
            proxy,
            lamb=0.45,
            nu=-0.47,
            iterations=smoothing_iterations,
        )
    trimesh.repair.fix_normals(proxy, multibody=False)
    proxy.remove_unreferenced_vertices()
    if not proxy.is_watertight:
        raise MeshRepairError(
            "Volumetric wrapping did not produce a closed manifold at this resolution."
        )

    rms, p95, maximum = _surface_deviation(working, proxy)
    diagnostics = ProxyDiagnostics(
        method="voxel_wrap",
        boundary_loops_filled=fill_result.loops_filled,
        voxel_resolution=resolution,
        voxel_pitch=pitch,
        closing_radius_voxels=closing_radius_voxels,
        smoothing_iterations=smoothing_iterations,
        rms_deviation=rms,
        p95_deviation=p95,
        max_deviation=maximum,
        normalized_rms_percent=100.0 * rms / longest,
    )
    return proxy, diagnostics
