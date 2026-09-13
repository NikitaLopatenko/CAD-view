import numpy as np
import trimesh

from mesh_repair import (
    boundary_edge_count,
    create_watertight_proxy,
    fill_boundary_loops,
)


def _sphere_with_large_opening() -> trimesh.Trimesh:
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    centroids = mesh.triangles_center
    mesh.update_faces(centroids[:, 2] < 0.72)
    mesh.remove_unreferenced_vertices()
    return mesh


def test_fill_boundary_loops_handles_more_than_quad_holes() -> None:
    mesh = _sphere_with_large_opening()
    assert not mesh.is_watertight
    assert boundary_edge_count(mesh) > 4

    result = fill_boundary_loops(mesh)

    assert result.loops_found == 1
    assert result.loops_filled == 1
    assert result.faces_added > 2
    assert boundary_edge_count(mesh) == 0
    assert mesh.is_watertight


def test_watertight_proxy_is_separate_and_reports_deviation() -> None:
    source = _sphere_with_large_opening()
    source_vertices = np.asarray(source.vertices).copy()
    source_faces = np.asarray(source.faces).copy()

    proxy, diagnostics = create_watertight_proxy(
        source,
        resolution=72,
        closing_radius_voxels=1,
        smoothing_iterations=2,
    )

    assert proxy.is_watertight
    assert len(proxy.split(only_watertight=False)) == 1
    assert diagnostics.method == "voxel_wrap"
    assert diagnostics.boundary_loops_filled == 1
    assert diagnostics.rms_deviation > 0
    assert diagnostics.p95_deviation >= diagnostics.rms_deviation * 0.5
    np.testing.assert_array_equal(source.vertices, source_vertices)
    np.testing.assert_array_equal(source.faces, source_faces)
