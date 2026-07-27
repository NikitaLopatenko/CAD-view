from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageFilter

PROJECT_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_DIR / "tools"
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CAD-View"
MESHROOM_RUNTIME = RUNTIME_ROOT / "Meshroom"
JOBS_ROOT = RUNTIME_ROOT / "jobs"
MINIMUM_IMAGE_COUNT = 6
# Light edge pad only for dense-stage masks. Do NOT grow to a coverage floor:
# full-frame SfM already uses the background for pose.
DENSE_MASK_EDGE_RATIO = 0.03
DENSE_MASK_MAX_RATIO = 0.06
# Legacy / diagnostic pose-context dilation (kept for tests and tooling).
MASK_CONTEXT_RATIO = 0.08
MIN_MASK_COVERAGE = 0.15
MAX_MASK_CONTEXT_RATIO = 0.35


class ReconstructionError(RuntimeError):
    pass


def dilate_mask(
    mask: Image.Image,
    ratio: float = MASK_CONTEXT_RATIO,
    *,
    min_coverage: float = MIN_MASK_COVERAGE,
    max_ratio: float = MAX_MASK_CONTEXT_RATIO,
) -> Image.Image:
    """Grow white foreground so SfM can use surrounding texture for camera pose."""
    import numpy as np

    mask = mask.convert("L")
    binary = np.asarray(mask) > 127
    if not binary.any():
        return Image.new("L", mask.size, 0)

    ys, xs = np.where(binary)
    width, height = mask.size
    min_dim = min(width, height)
    coverage = float(binary.mean())
    # Grow until the context window covers enough of the frame for pose, or
    # until we hit the maximum pad. Small/distant objects need larger pads.
    pad_ratio = max(float(ratio), 0.0)
    if coverage < min_coverage:
        pad_ratio = max(pad_ratio, min(max_ratio, 0.18 + (min_coverage - coverage)))

    pad = max(8, int(round(min_dim * pad_ratio)))
    x0 = max(0, int(xs.min()) - pad)
    y0 = max(0, int(ys.min()) - pad)
    x1 = min(width, int(xs.max()) + pad + 1)
    y1 = min(height, int(ys.max()) + pad + 1)

    # If the padded box is still too small, expand symmetrically toward a
    # coverage floor so textured surroundings (grid paper, desk grain) remain.
    box_coverage = ((x1 - x0) * (y1 - y0)) / float(width * height)
    if box_coverage < min_coverage:
        target_area = min_coverage * width * height
        aspect = max(1.0, (x1 - x0) / max(1, y1 - y0))
        target_h = int(round((target_area / aspect) ** 0.5))
        target_w = int(round(target_h * aspect))
        cx = 0.5 * (x0 + x1)
        cy = 0.5 * (y0 + y1)
        x0 = max(0, int(round(cx - target_w / 2)))
        y0 = max(0, int(round(cy - target_h / 2)))
        x1 = min(width, x0 + target_w)
        y1 = min(height, y0 + target_h)
        x0 = max(0, x1 - target_w)
        y0 = max(0, y1 - target_h)

    expanded = Image.new("L", mask.size, 0)
    # Keep the precise SAM silhouette and also a padded context window.
    expanded.paste(mask.point(lambda value: 255 if value > 127 else 0))
    context = Image.new("L", (x1 - x0, y1 - y0), 255)
    expanded.paste(context, (x0, y0))
    # Soft morphological grow so the context window is not a hard rectangle only.
    return expanded.filter(ImageFilter.MaxFilter(15))


def _ensure_meshroom_runtime() -> Path | None:
    """Prefer an ASCII-only Meshroom path; AliceVision breaks on Cyrillic folders."""
    configured = os.environ.get("MESHROOM_BATCH_PATH")
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.is_file():
            return path

    runtime_exe = MESHROOM_RUNTIME / "meshroom_batch.exe"
    if runtime_exe.is_file():
        return runtime_exe

    source_root = TOOLS_DIR / "Meshroom-2023.3.0"
    if not source_root.is_dir():
        match = next(TOOLS_DIR.rglob("meshroom_batch.exe"), None) if TOOLS_DIR.exists() else None
        if match is None:
            return None
        source_root = match.parent

    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    if MESHROOM_RUNTIME.exists() or MESHROOM_RUNTIME.is_symlink():
        try:
            if MESHROOM_RUNTIME.is_dir() and not MESHROOM_RUNTIME.is_symlink():
                # Unexpected real directory; leave it alone and fall back.
                pass
            else:
                MESHROOM_RUNTIME.unlink(missing_ok=True)
        except OSError:
            pass

    if not runtime_exe.is_file():
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(MESHROOM_RUNTIME), str(source_root)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 and not runtime_exe.is_file():
            raise ReconstructionError(
                "Could not create ASCII Meshroom junction under LocalAppData. "
                f"{result.stderr or result.stdout}"
            )

    return runtime_exe if runtime_exe.is_file() else None


def find_meshroom_batch() -> Path | None:
    try:
        return _ensure_meshroom_runtime()
    except ReconstructionError:
        if not TOOLS_DIR.exists():
            return None
        names = (
            "meshroom_batch.exe",
            "meshroom_photogrammetry.exe",
            "meshroom_batch.bat",
            "meshroom_batch",
            "meshroom_photogrammetry",
        )
        for name in names:
            match = next(TOOLS_DIR.rglob(name), None)
            if match is not None:
                return match
        return None


def reconstruction_capabilities() -> dict[str, object]:
    from neural_reconstruction import neural_reconstruction_capabilities

    executable = find_meshroom_batch()
    meshroom_available = executable is not None
    neural = neural_reconstruction_capabilities()
    neural_available = bool(neural.get("neural_available"))
    any_engine = meshroom_available or neural_available
    return {
        "engine": "dual",
        "engines": ["auto", "meshroom", "vggt"],
        "available": any_engine,
        "meshroom_available": meshroom_available,
        "executable": str(executable) if executable else None,
        "supports_photos": any_engine,
        "supports_video": any_engine,
        "minimum_image_count": MINIMUM_IMAGE_COUNT,
        "provenance_class": "photogrammetry_reconstructed",
        "runtime_root": str(RUNTIME_ROOT),
        **neural,
    }


def extract_video_frames(video_path: Path, image_dir: Path) -> list[Path]:
    image_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    pattern = image_dir / "frame-%06d.jpg"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        "fps=2",
        "-frames:v",
        "240",
        "-q:v",
        "2",
        str(pattern),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30 * 60,
        check=False,
    )
    if result.returncode != 0:
        raise ReconstructionError(
            f"Video frame extraction failed: {result.stderr[-1000:]}"
        )

    frames = sorted(image_dir.glob("frame-*.jpg"))
    if len(frames) < MINIMUM_IMAGE_COUNT:
        raise ReconstructionError(
            f"Video produced {len(frames)} usable frames; "
            f"at least {MINIMUM_IMAGE_COUNT} are required."
        )
    return frames


def _ascii_job_dirs(job_id: str) -> tuple[Path, Path, Path]:
    job_dir = JOBS_ROOT / job_id
    image_dir = job_dir / "images"
    output_dir = job_dir / "output"
    cache_dir = job_dir / "cache"
    return image_dir, output_dir, cache_dir


def stage_masks_for_meshroom(
    source_mask_dir: Path,
    job_id: str,
    *,
    dilate: bool = True,
    mode: str = "dense",
) -> Path:
    """
    Stage masks for Meshroom.

    mode=\"dense\": small edge grow only; used by PrepareDenseScene after
    full-frame SfM so the object silhouette does not starve camera pose.
    mode=\"pose_context\": legacy large context window (diagnostic / unused by
    the primary pipeline).
    """
    label = "masks_dense" if mode == "dense" else "masks_dilated"
    mask_dir = JOBS_ROOT / job_id / label
    if mask_dir.exists():
        shutil.rmtree(mask_dir)
    mask_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(source_mask_dir.glob("*.png")):
        with Image.open(path) as opened:
            opened.load()
            if not dilate:
                prepared = opened.convert("L")
            elif mode == "dense":
                prepared = dilate_mask(
                    opened,
                    ratio=DENSE_MASK_EDGE_RATIO,
                    min_coverage=0.0,
                    max_ratio=DENSE_MASK_MAX_RATIO,
                )
            else:
                prepared = dilate_mask(opened)
            prepared.save(mask_dir / path.name, format="PNG")
    return mask_dir


def mask_foreground_coverage(mask_dir: Path) -> float | None:
    """Mean foreground fraction across PNG masks, or None when empty."""
    import numpy as np

    coverages: list[float] = []
    for path in sorted(mask_dir.glob("*.png")):
        with Image.open(path) as opened:
            coverages.append(float((np.asarray(opened.convert("L")) > 127).mean()))
    if not coverages:
        return None
    return float(sum(coverages) / len(coverages))


def stage_images_for_meshroom(source_image_dir: Path, job_id: str) -> Path:
    """Copy inputs into an ASCII LocalAppData workspace before launching Meshroom."""
    image_dir, _, _ = _ascii_job_dirs(job_id)
    if image_dir.exists():
        shutil.rmtree(image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(source_image_dir.iterdir()):
        if path.is_file():
            shutil.copy2(path, image_dir / path.name)
    return image_dir


def _summarize_meshroom_failure(stdout: str, stderr: str) -> str:
    combined = f"{stdout}\n{stderr}"
    lowered = combined.lower()
    if "cannot be accessed" in lowered or "??????" in combined:
        return (
            "Meshroom could not access its install path. "
            "Non-ASCII folders (for example Cyrillic Desktop names) break AliceVision; "
            "CAD-View now reroutes Meshroom through LocalAppData."
        )
    if "camerainit failed" in lowered:
        return (
            "Meshroom CameraInit failed. Use at least 6 overlapping photos of a "
            "textured, rigid object with varied viewpoints."
        )
    if _looks_like_sfm_collapse(stdout, stderr):
        return (
            "Photogrammetry matched features across views, but Structure-from-Motion "
            "collapsed to zero cameras/landmarks. Common causes: the object fills too "
            "little of the frame, large viewpoint jumps, motion blur, or a "
            "glossy/low-texture surface with too little surrounding context. "
            "Fill 40–70% of the frame with the object, keep 60–80% overlap, leave "
            "textured background visible for pose, then retry; CAD-View will also "
            "fall through to the VGGT neural engine when available."
        )
    if "no valid tracks" in lowered or "0 geometric image pair matches" in lowered:
        return (
            "Photogrammetry found features but could not link cameras into a "
            "consistent 3D track network. Common causes: glossy/low-texture object, "
            "large viewpoint jumps, or motion blur. Reshoot with sticky dots or "
            "marker tape on the object and keep 60–80% overlap between stills."
        )
    if (
        "depth map fusion gives an empty result" in lowered
        or "no valid mesh was generated" in lowered
        or "filtered to 0 points" in lowered
        or "bounding box is too small" in lowered
        or "failed to estimate space from sfm" in lowered
    ):
        return (
            "Cameras calibrated, but dense meshing produced no usable surface "
            "(0 facets / empty fusion). Typical for tiny, glossy, or low-texture "
            "objects even after full-frame SfM. CAD-View retries without dense "
            "masks and then routes to VGGT neural reconstruction when available."
        )
    detail = (stderr or stdout).strip()
    if not detail:
        return "Meshroom exited with an unknown error."
    return detail[-500:]


def _looks_like_weak_meshing_failure(stdout: str, stderr: str) -> bool:
    lowered = f"{stdout}\n{stderr}".lower()
    return any(
        token in lowered
        for token in (
            "depth map fusion gives an empty result",
            "no valid mesh was generated",
            "filtered to 0 points",
            "bounding box is too small",
            "failed to estimate space from sfm",
        )
    )


def _looks_like_sfm_collapse(stdout: str, stderr: str) -> bool:
    """True when FeatureMatching found tracks but incremental SfM ended empty."""
    combined = f"{stdout}\n{stderr}"
    lowered = combined.lower()
    if "structurefrommotion" not in lowered and "incremental reconstruction" not in lowered:
        # Still allow landmark/pose fingerprints from truncated UI error snippets.
        pass
    return (
        "# landmarks: 0" in lowered
        or "# cameras calibrated: 0" in lowered
        or "# poses: 0" in lowered
        or (
            "incremental reconstruction completed" in lowered
            and "# number of landmarks: 0" in lowered
        )
    )


def _looks_like_track_failure(stdout: str, stderr: str) -> bool:
    lowered = f"{stdout}\n{stderr}".lower()
    return (
        "no valid tracks" in lowered
        or "0 geometric image pair matches" in lowered
        or _looks_like_sfm_collapse(stdout, stderr)
    )


def _write_meshroom_overrides(
    path: Path,
    *,
    dense_mask_dir: Path | None,
) -> Path:
    """
    Full-frame SfM, object-only dense reconstruction.

    Masks are applied in PrepareDenseScene (not FeatureExtraction) so AliceVision
    can use background texture for camera pose, then densify the object ROI.
    """
    import json

    meshing: dict[str, object] = {
        "estimateSpaceMinObservationAngle": 5.0,
        "estimateSpaceMinObservations": 2,
        "minStep": 1,
        "minVis": 1,
        "addLandmarksToTheDensePointCloud": True,
        "maskBorderSize": 4,
        "maxNbConnectedHelperPoints": 50,
        # Weight > 0 enables silhouette helper points on depth-map mask borders.
        "maskHelperPointsWeight": 2.0 if dense_mask_dir is not None else 0.0,
    }
    payload: dict[str, dict[str, object]] = {
        "Meshing_1": meshing,
        "DepthMapFilter_1": {
            "minNumOfConsistentCams": 2,
        },
        "FeatureExtraction_1": {
            # Keep features dense; never attach masksFolder here.
            "describerPreset": "high",
        },
    }
    if dense_mask_dir is not None:
        payload["PrepareDenseScene_1"] = {
            "masksFolders": [str(dense_mask_dir.resolve()).replace("\\", "/")],
            "maskExtension": "png",
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def run_meshroom(
    image_dir: Path,
    output_dir: Path,
    log_path: Path,
    job_id: str | None = None,
    mask_dir: Path | None = None,
    default_field_of_view: float | None = None,
) -> Path:
    executable = find_meshroom_batch()
    if executable is None:
        raise ReconstructionError(
            "Meshroom is not installed. Set MESHROOM_BATCH_PATH or place "
            "the portable distribution under the project tools directory."
        )

    runtime_root = executable.parent
    alicevision_root = runtime_root / "aliceVision"
    if job_id:
        staged_images, staged_output, cache_dir = _ascii_job_dirs(job_id)
        if image_dir.resolve() != staged_images.resolve():
            staged_images = stage_images_for_meshroom(image_dir, job_id)
        if staged_output.exists():
            shutil.rmtree(staged_output)
        staged_output.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        work_images = staged_images
        work_output = staged_output
        work_cache = cache_dir
        source_masks = mask_dir
    else:
        work_images = image_dir
        work_output = output_dir
        work_cache = output_dir / "cache"
        source_masks = mask_dir
        work_output.mkdir(parents=True, exist_ok=True)
        work_cache.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["ALICEVISION_ROOT"] = str(alicevision_root)
    sensor_db = alicevision_root / "share" / "aliceVision" / "cameraSensors.db"
    if sensor_db.is_file():
        env["ALICEVISION_SENSOR_DB"] = str(sensor_db)

    # Architecture: full-frame FeatureExtraction/SfM → optional dense masks.
    # Never mask FeatureExtraction; that blinds the solver to background texture.
    attempts: list[tuple[str, Path | None]] = []
    if source_masks is not None:
        if job_id:
            dense_masks = stage_masks_for_meshroom(
                source_masks, job_id, mode="dense"
            )
        else:
            dense_masks = work_output / "masks_dense"
            if dense_masks.exists():
                shutil.rmtree(dense_masks)
            dense_masks.mkdir(parents=True, exist_ok=True)
            for path in sorted(source_masks.glob("*.png")):
                with Image.open(path) as opened:
                    opened.load()
                    dilate_mask(
                        opened,
                        ratio=DENSE_MASK_EDGE_RATIO,
                        min_coverage=0.0,
                        max_ratio=DENSE_MASK_MAX_RATIO,
                    ).save(dense_masks / path.name, format="PNG")
        coverage = mask_foreground_coverage(source_masks)
        if coverage is not None and coverage < 0.08:
            log_chunks_preamble = (
                f"NOTE object_mask_coverage={coverage:.4f} "
                "(object fills little of the frame; full-frame SfM uses the "
                "background for pose, dense masks stay object-focused)\n\n"
            )
        else:
            log_chunks_preamble = ""
        attempts.append(("scene_pose_object_dense", dense_masks))
        attempts.append(("fully_unmasked", None))
    else:
        log_chunks_preamble = ""
        attempts.append(("plain", None))

    pipelines = ("photogrammetry", "photogrammetryDraft")
    log_chunks: list[str] = [log_chunks_preamble] if log_chunks_preamble else []
    last_stdout = ""
    last_stderr = ""

    for mask_label, dense_masks in attempts:
        for pipeline in pipelines:
            # Keep one cache root for the full pipeline so successful SfM nodes
            # can be reused when only dense overrides change. Draft uses a fork.
            pipeline_cache = (
                work_cache
                if pipeline == "photogrammetry"
                else work_cache / f"{mask_label}_{pipeline}"
            )
            if pipeline_cache.exists() and pipeline_cache != work_cache:
                shutil.rmtree(pipeline_cache)
            pipeline_cache.mkdir(parents=True, exist_ok=True)

            overrides_path = pipeline_cache / f"overrides_{mask_label}.json"
            _write_meshroom_overrides(overrides_path, dense_mask_dir=dense_masks)

            command = [
                str(executable),
                "--input",
                str(work_images),
                "--output",
                str(work_output),
                "--cache",
                str(pipeline_cache),
                "--pipeline",
                pipeline,
                "--overrides",
                str(overrides_path),
            ]
            if default_field_of_view is not None and default_field_of_view > 0:
                command.extend(
                    [
                        "--paramOverrides",
                        f"CameraInit:defaultFieldOfView={default_field_of_view:.4f}",
                    ]
                )
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=12 * 60 * 60,
                check=False,
                env=env,
                cwd=str(runtime_root),
            )
            last_stdout = result.stdout
            last_stderr = result.stderr
            log_chunks.append(
                f"ATTEMPT {mask_label} PIPELINE {pipeline}\n"
                f"COMMAND\n{' '.join(command)}\n\n"
                f"STDOUT\n{result.stdout}\n\nSTDERR\n{result.stderr}"
            )
            log_path.write_text("\n\n====\n\n".join(log_chunks), encoding="utf-8")

            if result.returncode == 0:
                break
            track_failed = _looks_like_track_failure(result.stdout, result.stderr)
            weak_mesh = _looks_like_weak_meshing_failure(result.stdout, result.stderr)
            if track_failed:
                # Full-frame SfM already failed; draft reuses the same SfM stage.
                break
            if pipeline == "photogrammetry" and weak_mesh:
                # Dense meshing collapsed; try draft meshing from the sparse cloud.
                continue
            if dense_masks is not None and weak_mesh:
                # Object-only dense fusion failed; retry densifying the full scene.
                break
            raise ReconstructionError(
                _summarize_meshroom_failure(result.stdout, result.stderr)
            )
        else:
            continue
        if result.returncode == 0:
            break
    else:
        raise ReconstructionError(
            _summarize_meshroom_failure(last_stdout, last_stderr)
        )

    # Copy published meshes back into the caller's output directory when staged.
    if job_id and work_output.resolve() != output_dir.resolve():
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in work_output.rglob("*"):
            if path.is_file():
                destination = output_dir / path.relative_to(work_output)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)

    search_roots = [output_dir, work_output]
    for root in search_roots:
        for suffix in ("*.obj", "*.stl", "*.ply"):
            candidates = [path for path in root.rglob(suffix) if path.is_file()]
            if candidates:
                return max(candidates, key=lambda path: path.stat().st_size)
    raise ReconstructionError("Meshroom completed without publishing a mesh.")
