from __future__ import annotations

import json

import numpy as np
from PIL import Image


def test_dilate_mask_grows_tiny_object_to_pose_coverage() -> None:
    from reconstruction import MIN_MASK_COVERAGE, dilate_mask

    mask = Image.new("L", (1920, 2560), 0)
    # ~2% coverage bottle-sized blob, matching the failed Optinol capture.
    for y in range(1500, 1900):
        for x in range(880, 1040):
            mask.putpixel((x, y), 255)

    dilated = dilate_mask(mask)
    coverage = (np.asarray(dilated) > 127).mean()
    assert coverage >= MIN_MASK_COVERAGE
    assert coverage > 0.1


def test_dense_mask_staging_keeps_object_focused(monkeypatch, tmp_path) -> None:
    import reconstruction

    monkeypatch.setattr(reconstruction, "JOBS_ROOT", tmp_path)
    source = tmp_path / "source_masks"
    source.mkdir()
    mask = Image.new("L", (1920, 2560), 0)
    for y in range(1500, 1900):
        for x in range(880, 1040):
            mask.putpixel((x, y), 255)
    mask.save(source / "image-0001.png")

    dense = reconstruction.stage_masks_for_meshroom(source, "job-dense", mode="dense")
    coverage = (np.asarray(Image.open(dense / "image-0001.png").convert("L")) > 127).mean()
    # Dense masks stay near the object; they must not jump to the 15% pose floor.
    assert coverage < 0.08


def test_sfm_collapse_detected_from_zero_landmarks_log() -> None:
    from reconstruction import (
        _looks_like_sfm_collapse,
        _looks_like_track_failure,
        _summarize_meshroom_failure,
    )

    stderr = (
        "Incremental Reconstruction completed with 2 iterations:\n"
        "\t- # number of landmarks: 0\n"
        "[info] # landmarks: 0\n"
        "[info] # cameras calibrated: 0\n"
        "[info] # poses: 0\n"
    )
    assert _looks_like_sfm_collapse("", stderr)
    assert _looks_like_track_failure("", stderr)
    summary = _summarize_meshroom_failure("", stderr)
    assert "zero cameras/landmarks" in summary.lower()


def test_meshroom_overrides_use_dense_masks_not_feature_masks(tmp_path) -> None:
    from reconstruction import _write_meshroom_overrides

    mask_dir = tmp_path / "masks_dense"
    mask_dir.mkdir()
    path = _write_meshroom_overrides(
        tmp_path / "overrides.json", dense_mask_dir=mask_dir
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "PrepareDenseScene_1" in payload
    assert payload["PrepareDenseScene_1"]["masksFolders"]
    assert payload["Meshing_1"]["maskHelperPointsWeight"] == 2.0
    assert payload["Meshing_1"]["estimateSpaceMinObservations"] == 2
    assert payload["Meshing_1"]["minStep"] == 1
    assert "masksFolder" not in json.dumps(payload.get("FeatureExtraction_1", {}))


def _stub_meshroom_runtime(monkeypatch, tmp_path, fake_run):
    import reconstruction

    executable = tmp_path / "meshroom_batch.exe"
    executable.write_text("", encoding="utf-8")
    alice = tmp_path / "aliceVision" / "share" / "aliceVision"
    alice.mkdir(parents=True)
    (alice / "cameraSensors.db").write_text("", encoding="utf-8")

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    Image.new("RGB", (64, 64), (10, 20, 30)).save(image_dir / "a.jpg")

    mask_dir = tmp_path / "masks"
    mask_dir.mkdir()
    tiny = Image.new("L", (64, 64), 0)
    for y in range(28, 36):
        for x in range(28, 36):
            tiny.putpixel((x, y), 255)
    tiny.save(mask_dir / "a.png")

    output_dir = tmp_path / "output"
    log_path = tmp_path / "meshroom.log"

    monkeypatch.setattr(reconstruction, "find_meshroom_batch", lambda: executable)
    monkeypatch.setattr(reconstruction.subprocess, "run", fake_run)
    monkeypatch.setattr(
        reconstruction,
        "stage_images_for_meshroom",
        lambda source, job_id: image_dir,
    )
    monkeypatch.setattr(
        reconstruction,
        "stage_masks_for_meshroom",
        lambda source, job_id, dilate=True, mode="dense": mask_dir,
    )
    monkeypatch.setattr(
        reconstruction,
        "_ascii_job_dirs",
        lambda job_id: (image_dir, output_dir, tmp_path / "cache"),
    )
    return image_dir, mask_dir, output_dir, log_path


def test_run_meshroom_full_frame_then_unmasked_after_dense_failure(
    monkeypatch, tmp_path
) -> None:
    import reconstruction
    from pathlib import Path

    attempts: list[str] = []

    def fake_run(command, **kwargs):
        command_text = " ".join(str(part) for part in command)
        assert "FeatureExtraction:masksFolder" not in command_text
        overrides_path = Path(command[command.index("--overrides") + 1])
        overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
        dense = "PrepareDenseScene_1" in overrides
        draft = "photogrammetryDraft" in command_text
        attempts.append(
            ("dense" if dense else "unmasked") + ("-draft" if draft else "-full")
        )
        if dense:

            class Failed:
                returncode = 1
                stdout = ""
                stderr = "[fatal] No valid mesh was generated."

            return Failed()

        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        mesh_path = output_dir / "texturedMesh.obj"
        mesh_path.write_text("o mesh\n", encoding="utf-8")

        class Ok:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Ok()

    image_dir, mask_dir, output_dir, log_path = _stub_meshroom_runtime(
        monkeypatch, tmp_path, fake_run
    )
    result = reconstruction.run_meshroom(
        image_dir,
        output_dir,
        log_path,
        job_id="job-dense-fallback",
        mask_dir=mask_dir,
        default_field_of_view=69.0,
    )

    assert result.name == "texturedMesh.obj"
    assert attempts == ["dense-full", "dense-draft", "unmasked-full"]
    log_text = log_path.read_text(encoding="utf-8")
    assert "ATTEMPT scene_pose_object_dense" in log_text
    assert "ATTEMPT fully_unmasked" in log_text
    assert "FeatureExtraction:masksFolder" not in log_text
