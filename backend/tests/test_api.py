from io import BytesIO

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient
from PIL import Image

import main


def make_cube_stl() -> bytes:
    cube = trimesh.creation.box(extents=(10.0, 20.0, 30.0))
    exported = cube.export(file_type="stl")
    assert isinstance(exported, bytes)
    return exported


def make_open_cube_stl() -> bytes:
    cube = trimesh.creation.box(extents=(10.0, 20.0, 30.0))
    cube.update_faces(np.arange(len(cube.faces)) != 0)
    exported = cube.export(file_type="stl")
    assert isinstance(exported, bytes)
    return exported


def make_png(size: tuple[int, int] = (24, 16), value: int = 120) -> bytes:
    output = BytesIO()
    Image.new("L", size, value).save(output, format="PNG")
    return output.getvalue()


def test_list_meshes_returns_recent_uploads(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        first = client.post(
            "/api/meshes",
            files={"file": ("a.stl", make_cube_stl(), "model/stl")},
        ).json()
        second = client.post(
            "/api/meshes",
            files={"file": ("b.stl", make_cube_stl(), "model/stl")},
        ).json()
        response = client.get("/api/meshes")

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert second["id"] in ids
    assert first["id"] in ids
    assert ids.index(second["id"]) < ids.index(first["id"])


def test_upload_preserves_observed_mesh_and_reports_topology(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["provenance"]["geometry_state"] == "observed"
        assert payload["provenance"]["processing_steps"] == []
        assert payload["provenance"]["sha256"]
        assert payload["qualification"]["is_watertight"] is True
        assert payload["qualification"]["face_count"] == 12
        assert payload["qualification"]["extents"] == [10.0, 20.0, 30.0]
        assert payload["qualification"]["volume"] == 6000.0

        mesh_response = client.get(payload["download_url"])
        assert mesh_response.status_code == 200
        assert mesh_response.content == make_cube_stl()


def test_upload_rejects_unsupported_format(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/meshes",
            files={"file": ("part.step", BytesIO(b"not a mesh"), "application/step")},
        )

    assert response.status_code == 415


def test_upload_rejects_invalid_mesh(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/meshes",
            files={"file": ("broken.stl", b"not an stl", "model/stl")},
        )

    assert response.status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_scaling_creates_derived_mesh_with_lineage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        ).json()
        source_before = client.get(upload["download_url"]).content

        response = client.post(
            f"/api/meshes/{upload['id']}/scale",
            json={
                "point_a": [-5.0, 0.0, 0.0],
                "point_b": [5.0, 0.0, 0.0],
                "target_distance": 100.0,
                "unit": "mm",
            },
        )

        assert response.status_code == 201
        scaled = response.json()
        assert scaled["id"] != upload["id"]
        assert scaled["unit"] == "mm"
        assert scaled["provenance"]["source_kind"] == "derived"
        assert scaled["provenance"]["geometry_state"] == "scaled"
        assert scaled["provenance"]["parent_id"] == upload["id"]
        assert scaled["provenance"]["processing_steps"] == ["uniform_scale"]
        assert scaled["qualification"]["extents"] == [100.0, 200.0, 300.0]
        assert scaled["qualification"]["volume"] == pytest.approx(6_000_000.0)
        assert scaled["scale_application"]["scale_factor"] == 10.0
        assert scaled["scale_application"]["residual"] == pytest.approx(0.0)
        assert client.get(upload["download_url"]).content == source_before


def test_scaling_rejects_coincident_anchor_points(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        ).json()
        files_before = set(tmp_path.iterdir())

        response = client.post(
            f"/api/meshes/{upload['id']}/scale",
            json={
                "point_a": [1.0, 1.0, 1.0],
                "point_b": [1.0, 1.0, 1.0],
                "target_distance": 25.0,
                "unit": "mm",
            },
        )

    assert response.status_code == 422
    assert set(tmp_path.iterdir()) == files_before


def test_scaling_rejects_nonpositive_target(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        ).json()
        response = client.post(
            f"/api/meshes/{upload['id']}/scale",
            json={
                "point_a": [0.0, 0.0, 0.0],
                "point_b": [1.0, 0.0, 0.0],
                "target_distance": 0,
                "unit": "mm",
            },
        )

    assert response.status_code == 422


def test_repair_can_fill_small_hole_without_modifying_source(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("damaged-cube.stl", make_open_cube_stl(), "model/stl")},
        ).json()
        source_before = client.get(upload["download_url"]).content
        assert upload["qualification"]["is_watertight"] is False

        response = client.post(
            f"/api/meshes/{upload['id']}/repair",
            json={"fill_small_holes": True},
        )

        assert response.status_code == 201
        repaired = response.json()
        assert repaired["provenance"]["geometry_state"] == "repaired"
        assert repaired["provenance"]["parent_id"] == upload["id"]
        assert repaired["qualification"]["is_watertight"] is True
        assert repaired["repair_report"]["faces_added"] == 1
        assert repaired["repair_report"]["requires_human_review"] is True
        assert repaired["repair_report"]["max_existing_vertex_displacement"] == 0
        assert client.get(upload["download_url"]).content == source_before


def test_conservative_repair_does_not_close_holes_by_default(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("open-cube.stl", make_open_cube_stl(), "model/stl")},
        ).json()
        response = client.post(
            f"/api/meshes/{upload['id']}/repair",
            json={},
        )

    assert response.status_code == 201
    repaired = response.json()
    assert repaired["qualification"]["is_watertight"] is False
    assert repaired["repair_report"]["faces_added"] == 0
    assert repaired["repair_report"]["requires_human_review"] is False
    assert "fill_small_holes" not in repaired["provenance"]["processing_steps"]


def test_watertight_proxy_reports_inference_and_preserves_source(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("open-cube.stl", make_open_cube_stl(), "model/stl")},
        ).json()
        source_before = client.get(upload["download_url"]).content
        response = client.post(
            f"/api/meshes/{upload['id']}/repair",
            json={
                "mode": "watertight_proxy",
                "voxel_resolution": 64,
                "closing_radius_voxels": 1,
                "smoothing_iterations": 2,
            },
        )

        assert response.status_code == 201
        proxy = response.json()
        assert proxy["qualification"]["is_watertight"] is True
        assert proxy["repair_report"]["method"] == "voxel_wrap"
        assert proxy["repair_report"]["normalized_rms_percent"] > 0
        assert proxy["repair_report"]["requires_human_review"] is True
        assert "watertight_voxel_wrap" in proxy["provenance"]["processing_steps"]
        assert client.get(upload["download_url"]).content == source_before


def test_check_constraint_reports_residual_and_persists(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        ).json()
        scaled = client.post(
            f"/api/meshes/{upload['id']}/scale",
            json={
                "point_a": [-5.0, 0.0, 0.0],
                "point_b": [5.0, 0.0, 0.0],
                "target_distance": 100.0,
                "unit": "mm",
            },
        ).json()

        response = client.post(
            f"/api/meshes/{scaled['id']}/checks",
            json={
                "label": "Overall height",
                "point_a": [0.0, -100.0, 0.0],
                "point_b": [0.0, 100.0, 0.0],
                "expected_distance": 199.0,
                "tolerance": 2.0,
            },
        )

        assert response.status_code == 201
        check = response.json()["check_constraints"][0]
        assert check["measured_distance"] == 200.0
        assert check["residual"] == 1.0
        assert check["relative_error_percent"] == pytest.approx(100 / 199)
        assert check["passes"] is True
        assert check["unit"] == "mm"
        persisted = client.get(f"/api/meshes/{scaled['id']}").json()
        assert persisted["check_constraints"] == response.json()["check_constraints"]


def test_check_constraint_can_fail_tolerance(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        ).json()
        scaled = client.post(
            f"/api/meshes/{upload['id']}/scale",
            json={
                "point_a": [-5.0, 0.0, 0.0],
                "point_b": [5.0, 0.0, 0.0],
                "target_distance": 100.0,
                "unit": "mm",
            },
        ).json()
        response = client.post(
            f"/api/meshes/{scaled['id']}/checks",
            json={
                "label": "Out of tolerance height",
                "point_a": [0.0, -100.0, 0.0],
                "point_b": [0.0, 100.0, 0.0],
                "expected_distance": 195.0,
                "tolerance": 1.0,
            },
        )

    assert response.status_code == 201
    assert response.json()["check_constraints"][0]["passes"] is False


def test_check_constraint_requires_scaled_units(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        ).json()
        response = client.post(
            f"/api/meshes/{upload['id']}/checks",
            json={
                "label": "Unknown units",
                "point_a": [0.0, 0.0, 0.0],
                "point_b": [1.0, 0.0, 0.0],
                "expected_distance": 1.0,
                "tolerance": 0.1,
            },
        )

    assert response.status_code == 409


def test_photo_reconstruction_queues_inputs_with_generated_names(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(main, "RECONSTRUCTION_DIR", tmp_path)
    monkeypatch.setattr(main, "_run_reconstruction_job", lambda _: None)
    photos = [
        ("files", (f"../../photo-{index}.jpg", b"jpeg-data", "image/jpeg"))
        for index in range(6)
    ]

    with TestClient(main.app) as client:
        response = client.post("/api/reconstructions/photos", files=photos)

        assert response.status_code == 202
        job = response.json()
        assert job["status"] == "queued"
        assert job["input_kind"] == "photo_set"
        assert job["input_count"] == 6
        persisted = client.get(f"/api/reconstructions/{job['id']}")
        assert persisted.status_code == 200

    stored_images = sorted((tmp_path / job["id"] / "images").iterdir())
    assert len(stored_images) == 6
    assert stored_images[0].name == "image-0001.jpg"


def test_mask_preview_returns_reviewable_png(monkeypatch) -> None:
    def fake_segment(image, box):
        assert image.size == (24, 16)
        assert box.x_min == pytest.approx(0.1)
        return Image.new("L", image.size, 255), "sam2"

    monkeypatch.setattr(main, "segment_with_box", fake_segment)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/reconstructions/mask-preview",
            files={"file": ("photo.png", make_png(), "image/png")},
            data={
                "box": (
                    '{"x_min":0.1,"y_min":0.2,"x_max":0.8,"y_max":0.9}'
                )
            },
        )

    assert response.status_code == 200
    assert response.headers["x-segmentation-mode"] == "sam2"
    with Image.open(BytesIO(response.content)) as mask:
        assert mask.size == (24, 16)


def test_photo_reconstruction_stores_reviewed_masks(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "RECONSTRUCTION_DIR", tmp_path)
    monkeypatch.setattr(main, "_run_reconstruction_job", lambda _: None)
    payload = [
        ("files", (f"photo-{index}.png", make_png(), "image/png"))
        for index in range(6)
    ] + [
        ("masks", (f"mask-{index}.png", make_png(value=255), "image/png"))
        for index in range(6)
    ]

    with TestClient(main.app) as client:
        response = client.post("/api/reconstructions/photos", files=payload)

    assert response.status_code == 202
    job_id = response.json()["id"]
    stored_masks = sorted((tmp_path / job_id / "masks").glob("*.png"))
    assert len(stored_masks) == 6
    assert stored_masks[0].name == "image-0001.png"


def test_photo_reconstruction_requires_minimum_coverage(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(main, "RECONSTRUCTION_DIR", tmp_path)
    photos = [
        ("files", (f"photo-{index}.jpg", b"jpeg-data", "image/jpeg"))
        for index in range(3)
    ]

    with TestClient(main.app) as client:
        response = client.post("/api/reconstructions/photos", files=photos)

    assert response.status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_video_reconstruction_rejects_unsupported_container(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(main, "RECONSTRUCTION_DIR", tmp_path)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/reconstructions/video",
            files={"file": ("capture.txt", b"not-video", "text/plain")},
        )

    assert response.status_code == 415


def test_box_primitive_analysis_and_step_export(monkeypatch, tmp_path) -> None:
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    upload_dir.mkdir()
    export_dir.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(main, "EXPORT_DIR", export_dir)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        ).json()
        scaled = client.post(
            f"/api/meshes/{upload['id']}/scale",
            json={
                "point_a": [-5.0, 0.0, 0.0],
                "point_b": [5.0, 0.0, 0.0],
                "target_distance": 100.0,
                "unit": "mm",
            },
        ).json()

        analysis = client.get(f"/api/meshes/{scaled['id']}/primitives")
        assert analysis.status_code == 200
        assert analysis.json()["fits"][0]["primitive_type"] == "box"
        assert analysis.json()["fits"][0]["normalized_rms"] == pytest.approx(0.0)

        response = client.post(
            f"/api/meshes/{scaled['id']}/step",
            json={"primitive_type": "box", "max_normalized_rms": 0.001},
        )
        assert response.status_code == 201
        exported = response.json()
        assert exported["unit"] == "mm"
        step = client.get(exported["download_url"])
        assert step.status_code == 200
        assert step.content.startswith(b"ISO-10303-21")


def test_declare_units_unlocks_step_without_physical_scale(
    monkeypatch, tmp_path
) -> None:
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    upload_dir.mkdir()
    export_dir.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(main, "EXPORT_DIR", export_dir)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        ).json()
        assert upload["unit"] is None

        blocked = client.post(
            f"/api/meshes/{upload['id']}/step",
            json={"primitive_type": "box", "max_normalized_rms": 0.05},
        )
        assert blocked.status_code == 409

        declared = client.post(
            f"/api/meshes/{upload['id']}/units",
            json={"unit": "mm"},
        ).json()
        assert declared["unit"] == "mm"
        assert declared["scale_application"] is None
        assert "declare_units" in declared["provenance"]["processing_steps"]
        assert declared["qualification"]["extents"] == upload["qualification"]["extents"]

        analysis = client.get(f"/api/meshes/{declared['id']}/primitives")
        assert analysis.status_code == 200
        assert analysis.json()["fits"][0]["primitive_type"] == "box"

        response = client.post(
            f"/api/meshes/{declared['id']}/step",
            json={"primitive_type": "box", "max_normalized_rms": 0.05},
        )
        assert response.status_code == 201
        step = client.get(response.json()["download_url"])
        assert step.status_code == 200
        assert step.content.startswith(b"ISO-10303-21")


def test_mesh_shape_step_preserves_non_primitive_silhouette(
    monkeypatch, tmp_path
) -> None:
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    upload_dir.mkdir()
    export_dir.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(main, "EXPORT_DIR", export_dir)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        ).json()
        declared = client.post(
            f"/api/meshes/{upload['id']}/units",
            json={"unit": "mm"},
        ).json()
        response = client.post(f"/api/meshes/{declared['id']}/step/mesh")
        assert response.status_code == 201
        payload = response.json()
        assert payload["primitive_type"] == "mesh_solid"
        step = client.get(payload["download_url"])
        assert step.status_code == 200
        assert step.content.startswith(b"ISO-10303-21")
        assert payload["fit"]["parameters"]["face_count_source"] == 12


def test_step_export_rejects_poor_primitive_fit(monkeypatch, tmp_path) -> None:
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    upload_dir.mkdir()
    export_dir.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(main, "EXPORT_DIR", export_dir)

    with TestClient(main.app) as client:
        upload = client.post(
            "/api/meshes",
            files={"file": ("reference-cube.stl", make_cube_stl(), "model/stl")},
        ).json()
        scaled = client.post(
            f"/api/meshes/{upload['id']}/scale",
            json={
                "point_a": [-5.0, 0.0, 0.0],
                "point_b": [5.0, 0.0, 0.0],
                "target_distance": 100.0,
                "unit": "mm",
            },
        ).json()
        response = client.post(
            f"/api/meshes/{scaled['id']}/step",
            json={"primitive_type": "cylinder", "max_normalized_rms": 0.001},
        )

    assert response.status_code == 422
    assert list(export_dir.iterdir()) == []
