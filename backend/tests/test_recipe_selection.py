import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from parametric_reconstruction import (
    ParametricReconstructionError,
    build_prismatic_recipe,
    write_solidworks_builder_script,
)
from recipe_selection import build_recipe, recipe_quality
from revolve_reconstruction import build_revolve_recipe
from solid_agreement import (
    boolean_backend_available,
    canonical_mesh,
    evaluate_candidate,
    residual_regions,
    symmetric_surface_agreement,
    volume_iou,
)


def _tall_stepped_sleeve() -> trimesh.Trimesh:
    """A tall turned part: the case the thinnest-axis heuristic gets wrong."""
    return trimesh.creation.revolve(
        np.array(
            [
                [0.0, 0.0],
                [7.0, 0.0],
                [7.0, 6.0],
                [5.0, 6.0],
                [5.0, 40.0],
                [0.0, 40.0],
            ]
        ),
        sections=128,
    )


def _bored_sleeve() -> trimesh.Trimesh:
    """A cup: solid below z=5, then a concentric bore open at the top."""
    return trimesh.creation.revolve(
        np.array(
            [
                [0.0, 0.0],
                [6.0, 0.0],
                [6.0, 30.0],
                [2.0, 30.0],
                [2.0, 5.0],
                [0.0, 5.0],
            ]
        ),
        sections=128,
    )


def _stepped_tube_with_radial_holes() -> trimesh.Trimesh:
    profile = np.array(
        [
            [7.0, -15.0],
            [10.0, -15.0],
            [10.0, -8.0],
            [9.0, -6.0],
            [9.0, 6.0],
            [10.0, 8.0],
            [10.0, 15.0],
            [7.0, 15.0],
            [7.0, -15.0],
        ]
    )
    body = trimesh.creation.revolve(profile, sections=96)
    cutters: list[trimesh.Trimesh] = []
    for axis, center in (
        ([1.0, 0.0, 0.0], [8.5, 0.0, -5.0]),
        ([0.0, 1.0, 0.0], [0.0, 8.5, 5.0]),
    ):
        cutter = trimesh.creation.cylinder(
            radius=1.5, height=4.0, sections=64
        )
        cutter.apply_transform(
            trimesh.geometry.align_vectors([0.0, 0.0, 1.0], axis)
        )
        cutter.apply_translation(center)
        cutters.append(cutter)
    return trimesh.boolean.difference([body, *cutters])


def test_volume_iou_is_one_for_a_solid_against_itself() -> None:
    mesh = trimesh.creation.box(extents=(10.0, 4.0, 3.0))

    assert volume_iou(mesh, mesh.copy()) == pytest.approx(1.0, abs=1e-6)


def test_volume_iou_falls_to_zero_for_disjoint_solids() -> None:
    left = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    right = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    right.apply_translation([50.0, 0.0, 0.0])

    assert volume_iou(left, right) == pytest.approx(0.0, abs=1e-9)


def test_unbuildable_candidate_scores_zero_instead_of_raising() -> None:
    report = evaluate_candidate(trimesh.creation.box(extents=(2.0, 2.0, 2.0)), None)

    assert report.score == 0.0
    assert report.method == "unbuildable"


def test_low_agreement_recipe_is_not_recommended_for_native_export() -> None:
    recipe = {
        "diagnostics": {
            "agreement": {"score": 0.24, "selection_score": 0.23}
        }
    }

    quality = recipe_quality(recipe)

    assert quality["status"] == "unsupported"
    assert quality["export_recommended"] is False
    assert quality["minimum_export_agreement"] == pytest.approx(0.60)


def test_symmetric_surface_agreement_penalizes_missing_local_detail() -> None:
    source = trimesh.creation.box(extents=(10.0, 10.0, 2.0))
    boss = trimesh.creation.box(extents=(2.0, 2.0, 1.0))
    boss.apply_translation([0.0, 0.0, 1.5])
    source = trimesh.boolean.union([source, boss])
    candidate = trimesh.creation.box(extents=(10.0, 10.0, 2.0))

    surface = symmetric_surface_agreement(source, candidate)

    assert surface["symmetric_tail_rms"] > 0.0
    assert surface["score"] < 1.0
    assert surface["source_to_candidate"]["max"] >= 0.9


def test_residual_regions_label_missing_and_excess_material() -> None:
    source = trimesh.creation.box(extents=(10.0, 10.0, 2.0))
    missing_boss = trimesh.creation.box(extents=(2.0, 2.0, 1.0))
    missing_boss.apply_translation([0.0, 0.0, 1.5])
    source = trimesh.boolean.union([source, missing_boss])

    candidate = trimesh.creation.box(extents=(10.0, 10.0, 2.0))
    excess_boss = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    excess_boss.apply_translation([4.0, 4.0, 1.5])
    candidate = trimesh.boolean.union([candidate, excess_boss])

    regions = residual_regions(source, candidate, normalized_tolerance=0.01)

    assert {region["kind"] for region in regions} == {
        "missing_material",
        "excess_material",
    }
    assert all(region["face_count"] > 0 for region in regions)
    assert all(region["max_distance"] > 0 for region in regions)


def test_candidate_selection_score_combines_volume_surface_and_normals() -> None:
    mesh = trimesh.creation.box(extents=(10.0, 4.0, 3.0))

    report = evaluate_candidate(mesh, mesh.copy())

    assert report.score == pytest.approx(1.0, abs=1e-6)
    assert report.selection_score == pytest.approx(1.0, abs=1e-6)
    assert report.surface_agreement["normal_alignment"] == pytest.approx(
        1.0, abs=1e-6
    )


def test_canonical_mesh_puts_the_chosen_axis_on_z_with_a_zero_base() -> None:
    mesh = trimesh.creation.box(extents=(60.0, 30.0, 2.0))
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    center = vertices.mean(axis=0)
    axes = np.eye(3)

    canonical = canonical_mesh(
        mesh, center=center, axes=axes, axial_index=0, axial_low=-30.0
    )

    assert canonical.bounds[0][2] == pytest.approx(0.0)
    assert canonical.bounds[1][2] == pytest.approx(60.0)
    assert canonical.volume == pytest.approx(mesh.volume, rel=1e-9)


def test_revolve_recovers_a_cylinder_as_a_four_point_profile() -> None:
    mesh = trimesh.creation.cylinder(radius=5.0, height=20.0, sections=96)

    recipe = build_revolve_recipe(mesh, "mm")

    feature = recipe["features"][0]
    assert feature["type"] == "revolve"
    assert feature["angle_degrees"] == pytest.approx(360.0)
    assert len(feature["sketch"]["outer_loop"]["points"]) == 4
    assert recipe["diagnostics"]["maximum_radius"] == pytest.approx(5.0, rel=0.01)
    assert recipe["diagnostics"]["bore_radius"] == pytest.approx(0.0)


def test_revolve_folds_a_concentric_bore_into_the_profile() -> None:
    recipe = build_revolve_recipe(_bored_sleeve(), "mm")

    diagnostics = recipe["diagnostics"]
    assert diagnostics["bore_radius"] == pytest.approx(2.0, rel=0.05)
    assert diagnostics["maximum_radius"] == pytest.approx(6.0, rel=0.05)
    assert any("bore" in warning for warning in recipe["warnings"])


def test_revolve_axis_defaults_to_the_roundest_axis_not_the_longest() -> None:
    # A washer's revolve axis is its shortest principal axis, so any rule based
    # on extent picks the wrong one here.
    mesh = trimesh.creation.annulus(r_min=4.0, r_max=12.0, height=2.0, sections=96)

    recipe = build_revolve_recipe(mesh, "mm")

    assert recipe["diagnostics"]["roundness_error"] < 0.01
    assert recipe["confidence"] > 0.95


def test_revolve_rejects_an_out_of_range_axis() -> None:
    with pytest.raises(ParametricReconstructionError, match="axis index"):
        build_revolve_recipe(
            trimesh.creation.box(extents=(4.0, 4.0, 4.0)), "mm", axis_index=7
        )


def test_prismatic_axis_can_be_forced_away_from_the_thinnest_span() -> None:
    # eigh orders principal axes by ascending variance, so axis 0 is always the
    # thinnest one and axis 2 the longest.
    mesh = trimesh.creation.box(extents=(60.0, 30.0, 2.0))

    default = build_prismatic_recipe(mesh, "mm")
    forced = build_prismatic_recipe(mesh, "mm", extrusion_index=2)

    assert default["diagnostics"]["extrusion_axis_index"] == 0
    assert default["features"][0]["depth"] == pytest.approx(2.0, rel=0.01)
    assert forced["diagnostics"]["extrusion_axis_index"] == 2
    assert forced["features"][0]["depth"] == pytest.approx(60.0, rel=0.01)


def test_confidence_reflects_measured_agreement_not_slenderness() -> None:
    # This cylinder is a flawless single extrude but is far from plate-like, so
    # the old slenderness-based confidence scored it zero.
    mesh = trimesh.creation.cylinder(radius=5.0, height=20.0, sections=96)

    recipe = build_prismatic_recipe(mesh, "mm", extrusion_index=2)

    assert recipe["confidence"] > 0.95
    assert recipe["diagnostics"]["thinness_confidence"] == pytest.approx(0.0)


@pytest.mark.skipif(
    not boolean_backend_available(), reason="volume IoU needs a boolean kernel"
)
def test_selection_prefers_a_revolve_for_a_tall_turned_part() -> None:
    recipe = build_recipe(_tall_stepped_sleeve(), "mm")

    assert recipe["strategy"] == "revolve_reconstruction"
    assert recipe["features"][0]["type"] == "revolve"
    assert recipe["confidence"] > 0.95

    search = recipe["diagnostics"]["hypothesis_search"]
    assert search["score_method"] == "volume_iou"
    assert search["selected"]["hypothesis"] == "revolve"
    # The old fixed heuristic extruded along the thinnest axis; it must have
    # been built, scored, and beaten rather than never considered.
    incumbent = search["incumbent"]
    assert incumbent["axis_index"] != search["selected"]["axis_index"]
    assert incumbent["score"] < recipe["confidence"]
    refinement = recipe["diagnostics"]["parameter_refinement"]
    assert refinement["parameter"] == "outer_radius_percentile"
    assert len(refinement["candidates"]) == 5
    assert len(refinement["profile_simplification"]["candidates"]) == 3


def test_selection_keeps_a_prismatic_history_for_a_plate() -> None:
    recipe = build_recipe(trimesh.creation.box(extents=(60.0, 30.0, 2.0)), "mm")

    assert recipe["strategy"] == "prismatic_extrusion"
    assert recipe["features"][0]["type"] == "extrude"
    assert recipe["confidence"] > 0.95


def test_selection_scores_every_axis_for_both_hypotheses() -> None:
    recipe = build_recipe(trimesh.creation.cylinder(radius=5.0, height=20.0), "mm")

    hypotheses = recipe["diagnostics"]["hypothesis_search"]["hypotheses"]
    assert len(hypotheses) == 6
    assert {item["hypothesis"] for item in hypotheses} == {"prismatic", "revolve"}
    assert {item["axis_index"] for item in hypotheses} == {0, 1, 2}
    assert sum(1 for item in hypotheses if item["selected"]) == 1
    assert hypotheses == sorted(
        hypotheses, key=lambda item: item["selection_score"], reverse=True
    )


def test_ties_within_the_margin_keep_the_simpler_prismatic_history() -> None:
    # A plain cylinder is equally well described as an extrude or a revolve.
    recipe = build_recipe(
        trimesh.creation.cylinder(radius=5.0, height=20.0, sections=96), "mm"
    )

    assert recipe["strategy"] == "prismatic_extrusion"


def test_selection_reports_the_runner_up_it_rejected() -> None:
    recipe = build_recipe(_tall_stepped_sleeve(), "mm")

    assert any("scored hypotheses" in warning for warning in recipe["warnings"])


def test_surface_axis_bore_continuity_and_radial_hole_beam() -> None:
    recipe = build_recipe(_stepped_tube_with_radial_holes(), "mm")

    diagnostics = recipe["diagnostics"]
    radial_holes = [
        feature
        for feature in recipe["features"]
        if feature["role"] == "radial_hole"
    ]
    assert diagnostics["revolve_axis_source"] == "surface_patch"
    assert diagnostics["bore_interpolated_slice_count"] > 0
    assert len(radial_holes) == 2
    assert {feature["direction_index"] for feature in radial_holes} == {0, 1}
    assert recipe["confidence"] > 0.99
    assert diagnostics["quality"]["export_recommended"] is True
    assert all(
        iteration["beam"][0]["kernel_valid"]
        for iteration in diagnostics["residual_refinement"]["iterations"][:2]
    )


def test_revolve_profile_follows_the_taper_instead_of_stair_stepping() -> None:
    # Sampling the radius at 96 heights must not leave 96 steps in the sketch;
    # a six-sided profile should come back with roughly six corners.
    recipe = build_revolve_recipe(_tall_stepped_sleeve(), "mm")

    points = recipe["features"][0]["sketch"]["outer_loop"]["points"]
    assert 4 <= len(points) <= 12
    assert recipe["diagnostics"]["profile_point_count"] == len(points)


def test_robust_revolve_radius_does_not_smear_a_local_tab_around_body() -> None:
    body = trimesh.creation.cylinder(radius=5.0, height=20.0, sections=96)
    tab = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    tab.apply_translation([5.5, 0.0, 0.0])
    mesh = trimesh.boolean.union([body, tab])

    robust = build_revolve_recipe(
        mesh, "mm", axis_index=2, outer_radius_percentile=50.0
    )
    maximum = build_revolve_recipe(
        mesh, "mm", axis_index=2, outer_radius_percentile=100.0
    )

    assert robust["confidence"] > maximum["confidence"]
    assert (
        robust["diagnostics"]["maximum_radius"]
        < robust["diagnostics"]["observed_maximum_radius"]
    )


def test_parametric_endpoint_serves_a_revolve_recipe(monkeypatch, tmp_path) -> None:
    import main

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)

    exported = _tall_stepped_sleeve().export(file_type="stl")
    assert isinstance(exported, bytes)

    with TestClient(main.app) as client:
        uploaded = client.post(
            "/api/meshes",
            files={"file": ("sleeve.stl", exported, "model/stl")},
        ).json()
        declared = client.post(
            f"/api/meshes/{uploaded['id']}/units", json={"unit": "mm"}
        ).json()

        response = client.get(f"/api/meshes/{declared['id']}/parametric")

    assert response.status_code == 200
    report = response.json()
    assert report["strategy"] == "revolve_reconstruction"
    assert report["features"][0]["type"] == "revolve"
    # The panel reads these without a depth, so they must survive serialisation.
    assert report["features"][0]["angle_degrees"] == 360.0
    assert "depth" not in report["features"][0]
    assert len(report["diagnostics"]["hypothesis_search"]["hypotheses"]) == 6


def test_solidworks_script_builds_a_native_revolve(tmp_path) -> None:
    recipe = build_revolve_recipe(_tall_stepped_sleeve(), "mm")
    script_path = tmp_path / "revolve.vbs"

    write_solidworks_builder_script(recipe, script_path)

    script = script_path.read_text(encoding="ascii")
    assert script_path.read_bytes().startswith(b"Option Explicit")
    assert "CreateCenterLine" in script
    assert script.count("FeatureRevolve2") == 1
    assert "selectionData.Mark = 4" in script
    assert "axisSegment.Select4 True, selectionData" in script
    assert "CADView Core Revolve" in script
    # 360 degrees expressed in radians for the SolidWorks API.
    assert "6.28318" in script


def test_solidworks_script_scales_the_revolve_centerline_to_metres(
    tmp_path,
) -> None:
    recipe = build_revolve_recipe(
        trimesh.creation.cylinder(radius=5.0, height=20.0, sections=96), "mm"
    )
    script_path = tmp_path / "revolve-units.vbs"

    write_solidworks_builder_script(recipe, script_path)

    script = script_path.read_text(encoding="ascii")
    centerline = next(
        line for line in script.splitlines() if "CreateCenterLine" in line
    )
    assert "0.02" in centerline
