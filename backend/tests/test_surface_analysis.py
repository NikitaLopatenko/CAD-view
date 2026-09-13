import pytest
import trimesh

from surface_analysis import analyze_surface_patches


def test_box_is_segmented_into_six_planar_patches() -> None:
    report = analyze_surface_patches(
        trimesh.creation.box(extents=(10.0, 8.0, 4.0))
    )

    assert report["patch_count"] == 6
    assert report["counts"]["plane"] == 6
    assert report["counts"]["cylinder"] == 0
    assert report["covered_area_fraction"] == pytest.approx(1.0)
    assert report["curvature_analysis"]["bands"]


def test_cylinder_has_a_cylindrical_barrel_and_planar_caps() -> None:
    report = analyze_surface_patches(
        trimesh.creation.cylinder(radius=5.0, height=12.0, sections=64)
    )

    assert report["counts"]["cylinder"] >= 1
    assert report["counts"]["plane"] >= 2
    barrel = next(
        patch
        for patch in report["patches"]
        if patch["surface_type"] == "cylinder"
    )
    assert barrel["fit"]["radius"] == pytest.approx(5.0, rel=0.02)
    assert barrel["fit"]["height"] == pytest.approx(12.0, rel=0.02)
    assert barrel["fit"]["normalized_rms"] < 0.01


def test_sharp_edges_are_not_merged_into_one_patch() -> None:
    report = analyze_surface_patches(
        trimesh.creation.box(extents=(2.0, 2.0, 2.0)),
        smooth_angle_degrees=5.0,
    )

    assert report["patch_count"] == 6
    assert all(
        patch["boundary_adjacency_count"] >= 4
        for patch in report["patches"]
    )


def test_empty_mesh_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty triangle mesh"):
        analyze_surface_patches(
            trimesh.Trimesh(vertices=[], faces=[], process=False)
        )
