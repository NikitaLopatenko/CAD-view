from pathlib import Path

from PIL import Image
from PIL.ExifTags import Base

import camera_intrinsics as ci


def _write_jpeg_with_exif(
    path: Path,
    *,
    make: str,
    model: str,
    focal_mm: float = 4.2,
    focal_35: int = 26,
) -> None:
    image = Image.new("RGB", (400, 300), (40, 80, 120))
    exif = Image.Exif()
    exif[Base.Make] = make
    exif[Base.Model] = model
    exif[Base.FocalLength] = (int(round(focal_mm * 1000)), 1000)
    exif[Base.FocalLengthIn35mmFilm] = focal_35
    image.save(path, format="JPEG", quality=95, exif=exif)


def test_horizontal_fov_from_35mm_equivalent() -> None:
    fov = ci.horizontal_fov_degrees(focal_length_35mm=26.0)
    assert fov is not None
    assert 65.0 < fov < 75.0


def test_sensor_db_lookup_prefers_exact_model(tmp_path, monkeypatch) -> None:
    database = tmp_path / "cameraSensors.db"
    database.write_text(
        "Apple;iPhone 12;5.6;cad-view-test\n"
        "Apple;iPhone 12 Pro Max;5.96;cad-view-test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ALICEVISION_SENSOR_DB", str(database))

    assert ci.lookup_sensor_width_mm("Apple", "iPhone 12") == 5.6
    assert ci.lookup_sensor_width_mm("Apple", "iPhone 12 Pro Max") == 5.96


def test_prepare_shared_camera_model_stamps_exif_and_fov(tmp_path, monkeypatch) -> None:
    database = tmp_path / "cameraSensors.db"
    database.write_text("Apple;iPhone 12;5.6;cad-view-test\n", encoding="utf-8")
    monkeypatch.setenv("ALICEVISION_SENSOR_DB", str(database))

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    for index in range(3):
        _write_jpeg_with_exif(
            image_dir / f"frame_{index:03d}.jpg",
            make="Apple",
            model="iPhone 12",
            focal_mm=4.2,
            focal_35=26,
        )

    estimate = ci.prepare_shared_camera_model(image_dir)

    assert estimate.make == "Apple"
    assert estimate.model == "iPhone 12"
    assert estimate.sensor_width_mm == 5.6
    assert estimate.horizontal_fov_deg is not None
    assert estimate.shared_intrinsic_recommended is True
    assert estimate.source == "exif"

    stamped = Image.open(image_dir / "frame_000.jpg").getexif()
    assert stamped.get(Base.Make) == "Apple"
    assert stamped.get(Base.Model) == "iPhone 12"


def test_missing_exif_uses_phone_fov_fallback(tmp_path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    for index in range(3):
        Image.new("RGB", (1920, 2560), (20, 30, 40)).save(
            image_dir / f"frame_{index:03d}.jpg", format="JPEG"
        )

    estimate = ci.prepare_shared_camera_model(image_dir)

    assert estimate.source == "phone_default"
    assert estimate.horizontal_fov_deg == ci.PHONE_DEFAULT_HORIZONTAL_FOV_DEG
    assert estimate.focal_length_35mm is not None
    stamped = Image.open(image_dir / "frame_000.jpg").getexif()
    assert stamped.get(Base.FocalLengthIn35mmFilm) is not None


def test_mesh_from_points_builds_triangle_mesh() -> None:
    import numpy as np
    from neural_reconstruction import _mesh_from_points

    rng = np.random.default_rng(0)
    # Hollow-ish shell of a box
    points = []
    for axis in range(3):
        for side in (0.0, 1.0):
            coords = rng.random((400, 3))
            coords[:, axis] = side
            points.append(coords)
    mesh = _mesh_from_points(np.vstack(points), pitch=0.08)
    assert len(mesh.faces) > 20
    assert len(mesh.vertices) > 20


def test_run_meshroom_passes_shared_fov_override(monkeypatch, tmp_path) -> None:
    import reconstruction

    executable = tmp_path / "meshroom_batch.exe"
    executable.write_text("", encoding="utf-8")
    alice = tmp_path / "aliceVision" / "share" / "aliceVision"
    alice.mkdir(parents=True)
    (alice / "cameraSensors.db").write_text("", encoding="utf-8")

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    Image.new("RGB", (32, 24), (10, 20, 30)).save(image_dir / "a.jpg")

    output_dir = tmp_path / "output"
    log_path = tmp_path / "meshroom.log"
    mesh_path = output_dir / "texturedMesh.obj"
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        output_dir.mkdir(parents=True, exist_ok=True)
        mesh_path.write_text("o mesh\n", encoding="utf-8")

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    monkeypatch.setattr(reconstruction, "find_meshroom_batch", lambda: executable)
    monkeypatch.setattr(reconstruction.subprocess, "run", fake_run)

    result = reconstruction.run_meshroom(
        image_dir,
        output_dir,
        log_path,
        default_field_of_view=69.4,
    )

    assert result == mesh_path
    command = captured["command"]
    assert isinstance(command, list)
    assert "--paramOverrides" in command
    assert "CameraInit:defaultFieldOfView=69.4000" in command
