import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

import main
from parametric_reconstruction import (
    ParametricReconstructionError,
    build_prismatic_recipe,
    write_solidworks_builder_script,
)


def _thin_box_stl() -> bytes:
    mesh = trimesh.creation.box(extents=(60.0, 30.0, 2.0))
    exported = mesh.export(file_type="stl")
    assert isinstance(exported, bytes)
    return exported


def _grooved_disc() -> trimesh.Trimesh:
    radial_axial_profile = np.array(
        [
            [0.0, -2.5],
            [10.0, -2.5],
            [10.0, -1.5],
            [9.0, -1.0],
            [8.0, 0.0],
            [9.0, 1.0],
            [10.0, 1.5],
            [10.0, 2.5],
            [0.0, 2.5],
        ]
    )
    return trimesh.creation.revolve(radial_axial_profile, sections=128)


def _ambiguous_stepped_disc() -> trimesh.Trimesh:
    radial_axial_profile = np.array(
        [
            [0.0, -2.5],
            [10.0, -2.5],
            [10.0, -1.0],
            [8.0, -1.0],
            [8.0, 1.0],
            [10.0, 1.0],
            [10.0, 2.5],
            [0.0, 2.5],
        ]
    )
    return trimesh.creation.revolve(radial_axial_profile, sections=128)


def test_prismatic_recipe_recovers_editable_sketch_and_depth() -> None:
    mesh = trimesh.creation.box(extents=(60.0, 30.0, 2.0))

    recipe = build_prismatic_recipe(mesh, "mm")

    assert recipe["strategy"] == "prismatic_extrusion"
    assert recipe["confidence"] > 0.9
    feature = recipe["features"][0]
    assert feature["type"] == "extrude"
    assert feature["depth"] == pytest.approx(2.0)
    assert len(feature["sketch"]["outer_loop"]["points"]) >= 4
    assert feature["sketch"]["inner_loops"] == []


def test_prismatic_recipe_recovers_through_hole_as_inner_loop() -> None:
    mesh = trimesh.creation.annulus(r_min=4.0, r_max=12.0, height=2.0, sections=96)

    recipe = build_prismatic_recipe(mesh, "mm")

    inner = recipe["features"][0]["sketch"]["inner_loops"]
    assert len(inner) == 1
    assert inner[0]["kind"] == "circle"
    assert inner[0]["radius"] == pytest.approx(4.0, rel=0.02)


def test_multi_section_recipe_detects_perimeter_groove_and_deviation() -> None:
    recipe = build_prismatic_recipe(_grooved_disc(), "mm")

    assert recipe["strategy"] == "sweep_cut_reconstruction"
    assert len(recipe["features"]) == 2
    assert recipe["features"][0]["role"] == "base"
    assert recipe["features"][0]["type"] == "extrude"
    assert recipe["features"][0]["end_condition"] == "midplane"
    assert recipe["features"][1]["role"] == "perimeter_groove_sweep"
    assert recipe["features"][1]["type"] == "sweep_cut"
    assert recipe["features"][1]["path"]["closed"] is False
    diagnostics = recipe["diagnostics"]
    assert diagnostics["groove_detected"] is True
    assert diagnostics["groove_width"] > 0
    assert diagnostics["volume_error_percent"] < 4.0
    assert len(diagnostics["sweep_candidates"]) == 1
    assert diagnostics["deviation"]["sample_count"] > 0
    intent = diagnostics["feature_intent"]["orthogonal_section_analysis"]
    assert intent["selected"] is True
    assert intent["hypotheses"][0]["score"] < intent["hypotheses"][1]["score"]


def test_solidworks_builder_writes_all_groove_features(tmp_path) -> None:
    recipe = build_prismatic_recipe(_grooved_disc(), "mm")
    script_path = tmp_path / "groove.vbs"

    write_solidworks_builder_script(recipe, script_path)

    script = script_path.read_text(encoding="ascii")
    assert script.count("FeatureExtrusion3") == 1
    assert script.count("InsertCutSwept5") == 1
    assert "CADView Perimeter Sweep Cut" in script
    assert 'False, 1, Nothing, 0)' in script
    assert 'True, 4, Nothing, 0)' in script
    assert "CADView-editable-" in script
    assert "2 native features" in script


def test_equivalent_sweep_and_stacked_histories_are_reported_ambiguous() -> None:
    recipe = build_prismatic_recipe(_ambiguous_stepped_disc(), "mm")

    intent = recipe["diagnostics"]["feature_intent"][
        "orthogonal_section_analysis"
    ]
    assert intent["decision"] == "ambiguous_equivalent"
    assert intent["selected"] is False
    assert recipe["strategy"] == "multi_section_perimeter_groove"
    assert recipe["features"][1]["type"] == "cut"


def test_solidworks_builder_script_contains_native_sketch_and_extrude(
    tmp_path,
) -> None:
    recipe = build_prismatic_recipe(
        trimesh.creation.annulus(r_min=4.0, r_max=12.0, height=2.0),
        "mm",
    )
    script_path = tmp_path / "build.vbs"

    write_solidworks_builder_script(recipe, script_path)

    script = script_path.read_text(encoding="ascii")
    assert script_path.read_bytes().startswith(b"Option Explicit")
    assert "CreateLine" in script
    assert "CreateCircleByRadius" in script
    assert "FeatureExtrusion3" in script
    assert "CADView-editable-" in script
    assert "CADView-builder-log.txt" in script
    assert "InsertSketch True" in script
    assert "InsertSketch2 True" in script
    assert "probe_line=" in script
    assert "SaveAs3" in script
    assert "Extension.SaveAs" not in script
    assert "CreateSpline2" not in script


def test_parametric_api_and_mocked_solidworks_export(
    monkeypatch, tmp_path
) -> None:
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    upload_dir.mkdir()
    export_dir.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(main, "EXPORT_DIR", export_dir)
    monkeypatch.setattr(main, "solidworks_available", lambda: True)

    captured: dict[str, object] = {}

    def fake_build(recipe, output_path: Path, *, visible: bool = False) -> None:
        captured["recipe"] = recipe
        captured["visible"] = visible
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"mock-sldprt")

    monkeypatch.setattr(main, "build_solidworks_part", fake_build)

    with TestClient(main.app) as client:
        uploaded = client.post(
            "/api/meshes",
            files={"file": ("thin-box.stl", _thin_box_stl(), "model/stl")},
        ).json()
        declared = client.post(
            f"/api/meshes/{uploaded['id']}/units",
            json={"unit": "mm"},
        ).json()

        analysis = client.get(f"/api/meshes/{declared['id']}/parametric")
        assert analysis.status_code == 200
        report = analysis.json()
        assert report["strategy"] == "prismatic_extrusion"
        assert report["features"][0]["type"] == "extrude"
        assert report["solidworks_available"] is True

        response = client.post(
            f"/api/meshes/{declared['id']}/solidworks",
            json={"visible": False},
        )
        assert response.status_code == 201
        exported = response.json()
        assert exported["feature_count"] == 1
        assert exported["artifact_type"] == "sldprt"
        assert captured["visible"] is False
        assert captured["recipe"]["strategy"] == "prismatic_extrusion"

        part = client.get(exported["download_url"])
        assert part.status_code == 200
        assert part.content == b"mock-sldprt"

        metadata = (
            export_dir / "solidworks" / f"{exported['id']}.json"
        ).read_text(encoding="utf-8")
        assert json.loads(metadata)["source_mesh_id"] == declared["id"]


def test_solidworks_api_falls_back_to_interactive_builder(
    monkeypatch, tmp_path
) -> None:
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    upload_dir.mkdir()
    export_dir.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(main, "EXPORT_DIR", export_dir)

    def fail_direct_build(*_args, **_kwargs) -> None:
        raise ParametricReconstructionError("No interactive sketch session.")

    monkeypatch.setattr(main, "build_solidworks_part", fail_direct_build)

    with TestClient(main.app) as client:
        uploaded = client.post(
            "/api/meshes",
            files={"file": ("thin-box.stl", _thin_box_stl(), "model/stl")},
        ).json()
        declared = client.post(
            f"/api/meshes/{uploaded['id']}/units",
            json={"unit": "mm"},
        ).json()

        response = client.post(
            f"/api/meshes/{declared['id']}/solidworks",
            json={"visible": True},
        )
        assert response.status_code == 201
        exported = response.json()
        assert exported["artifact_type"] == "builder_script"
        assert "double-click" in exported["warnings"][-1]

        script = client.get(exported["download_url"])
        assert script.status_code == 200
        assert b"FeatureExtrusion3" in script.content
