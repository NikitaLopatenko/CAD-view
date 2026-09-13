from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageFilter

from mesh_repair import fill_boundary_loops

RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CAD-View"
TRIPOSR_ROOT = RUNTIME_ROOT / "TripoSR"
TRIPOSR_PACKAGES = RUNTIME_ROOT / "triposr-packages"
TRIPOSR_REPO = "https://github.com/VAST-AI-Research/TripoSR.git"
TRIPOSR_MODEL_ID = os.environ.get("CAD_VIEW_TRIPOSR_MODEL", "stabilityai/TripoSR")
TRIPOSR_RESOLUTION = int(os.environ.get("CAD_VIEW_TRIPOSR_RESOLUTION", "192"))


class GenerativeReconstructionError(RuntimeError):
    pass


def _torch_available() -> bool:
    try:
        import torch

        return bool(torch)
    except (ImportError, OSError):
        return False


def triposr_source_available() -> bool:
    return (TRIPOSR_ROOT / "tsr" / "system.py").is_file()


def generative_reconstruction_capabilities() -> dict[str, object]:
    available = _torch_available()
    return {
        "generative_engine": "triposr",
        "generative_available": available,
        "generative_source_ready": triposr_source_available(),
        "generative_model": TRIPOSR_MODEL_ID,
        "generative_warning": (
            "Single-image shape prior; unobserved geometry is inferred, not measured."
        ),
    }


def ensure_triposr_runtime() -> Path:
    if not triposr_source_available():
        if shutil.which("git") is None:
            raise GenerativeReconstructionError(
                "Git is required for the first TripoSR setup."
            )
        TRIPOSR_ROOT.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", "--depth", "1", TRIPOSR_REPO, str(TRIPOSR_ROOT)],
            capture_output=True,
            text=True,
            timeout=10 * 60,
            check=False,
        )
        if result.returncode != 0 or not triposr_source_available():
            detail = (result.stderr or result.stdout).strip()[-800:]
            raise GenerativeReconstructionError(
                f"Could not install the TripoSR runtime. {detail}"
            )

    compatible_transformers = TRIPOSR_PACKAGES / "transformers" / "__init__.py"
    compatible_requests = TRIPOSR_PACKAGES / "requests" / "__init__.py"
    if not compatible_transformers.is_file() or not compatible_requests.is_file():
        TRIPOSR_PACKAGES.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--target",
                str(TRIPOSR_PACKAGES),
                "--no-deps",
                "transformers==4.35.0",
                "tokenizers==0.14.1",
                "huggingface-hub==0.17.3",
                "requests>=2.31",
                "certifi",
                "charset-normalizer",
                "idna",
                "urllib3",
            ],
            capture_output=True,
            text=True,
            timeout=10 * 60,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-800:]
            raise GenerativeReconstructionError(
                f"Could not install isolated TripoSR dependencies. {detail}"
            )
    return TRIPOSR_ROOT


def _matching_mask(image: Path, mask_dir: Path | None, index: int) -> Path | None:
    if mask_dir is None or not mask_dir.is_dir():
        return None
    candidates = (
        mask_dir / f"{image.stem}.png",
        mask_dir / f"image-{index + 1:04d}.png",
        mask_dir / f"mask-{index + 1:04d}.png",
    )
    match = next((candidate for candidate in candidates if candidate.is_file()), None)
    if match is not None:
        return match
    masks = sorted(mask_dir.glob("*.png"))
    return masks[index] if index < len(masks) else None


def _frame_score(image_path: Path, mask_path: Path | None) -> float:
    with Image.open(image_path) as opened:
        gray = opened.convert("L").resize((256, 256))
    edges = np.asarray(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    sharpness = float(np.var(edges)) / (255.0 * 255.0)
    if mask_path is None:
        return sharpness
    with Image.open(mask_path) as opened:
        mask = np.asarray(
            opened.convert("L").resize((256, 256), Image.Resampling.NEAREST)
        ) > 127
    area = float(mask.mean())
    if area <= 0.01:
        return -1.0
    border = float(
        np.mean(
            np.concatenate((mask[0], mask[-1], mask[:, 0], mask[:, -1]))
        )
    )
    # Prefer a large, sharp, fully visible object without rewarding extreme crops.
    area_score = 1.0 - min(abs(area - 0.42) / 0.42, 1.0)
    return area_score + 0.25 * sharpness - 2.0 * border


def select_scaffold_frame(
    image_dir: Path, mask_dir: Path | None
) -> tuple[Path, Path | None, float]:
    images = sorted(
        path
        for path in image_dir.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
    )
    if not images:
        raise GenerativeReconstructionError("TripoSR needs at least one image.")
    candidates = [
        (image, _matching_mask(image, mask_dir, index))
        for index, image in enumerate(images)
    ]
    scored = [
        (image, mask, _frame_score(image, mask)) for image, mask in candidates
    ]
    return max(scored, key=lambda value: value[2])


def _prepare_scaffold_input(
    image_path: Path, mask_path: Path | None, destination: Path
) -> None:
    with Image.open(image_path) as opened:
        rgb = opened.convert("RGB")
    if mask_path is None:
        rgb.thumbnail((512, 512), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (512, 512), (128, 128, 128))
        canvas.paste(rgb, ((512 - rgb.width) // 2, (512 - rgb.height) // 2))
        canvas.save(destination)
        return

    with Image.open(mask_path) as opened:
        mask = opened.convert("L").resize(rgb.size, Image.Resampling.NEAREST)
    bbox = mask.getbbox()
    if bbox is None:
        raise GenerativeReconstructionError("The selected scaffold mask is empty.")
    left, top, right, bottom = bbox
    margin = int(0.08 * max(right - left, bottom - top))
    box = (
        max(0, left - margin),
        max(0, top - margin),
        min(rgb.width, right + margin),
        min(rgb.height, bottom + margin),
    )
    crop = rgb.crop(box)
    alpha = mask.crop(box)
    scale = min(435 / crop.width, 435 / crop.height)
    size = (
        max(1, int(round(crop.width * scale))),
        max(1, int(round(crop.height * scale))),
    )
    crop = crop.resize(size, Image.Resampling.LANCZOS)
    alpha = alpha.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (512, 512), (128, 128, 128))
    offset = ((512 - size[0]) // 2, (512 - size[1]) // 2)
    canvas.paste(crop, offset, alpha)
    canvas.save(destination)


def run_triposr_reconstruction(
    image_dir: Path,
    output_dir: Path,
    *,
    mask_dir: Path | None = None,
    log_path: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    def report(stage: str) -> None:
        if progress is not None:
            progress(stage)

    report("generative_selecting_scaffold_view")
    source = ensure_triposr_runtime()
    selected, selected_mask, score = select_scaffold_frame(image_dir, mask_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared = output_dir / "scaffold_input.png"
    _prepare_scaffold_input(selected, selected_mask, prepared)

    report("generative_loading_triposr")
    raw_mesh = output_dir / "triposr_raw.obj"
    runner = Path(__file__).with_name("triposr_runner.py")
    command = [
        sys.executable,
        str(runner),
        "--source",
        str(source),
        "--packages",
        str(TRIPOSR_PACKAGES),
        "--image",
        str(prepared),
        "--output",
        str(raw_mesh),
        "--model",
        TRIPOSR_MODEL_ID,
        "--resolution",
        str(max(128, min(TRIPOSR_RESOLUTION, 256))),
        "--chunk-size",
        "4096",
    ]
    environment = os.environ.copy()
    environment.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    report("generative_inferring_scaffold")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30 * 60,
        check=False,
        env=environment,
    )
    log = (
        f"selected={selected.name} mask={selected_mask.name if selected_mask else None} "
        f"score={score:.6f}\ncommand={' '.join(command)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    if log_path is not None:
        log_path.write_text(log, encoding="utf-8")
    if result.returncode != 0 or not raw_mesh.is_file():
        detail = (result.stderr or result.stdout).strip()[-1200:]
        raise GenerativeReconstructionError(f"TripoSR failed. {detail}")

    report("generative_cleaning_scaffold")
    loaded = trimesh.load(raw_mesh, force="mesh", process=True)
    if not isinstance(loaded, trimesh.Trimesh) or loaded.is_empty:
        raise GenerativeReconstructionError("TripoSR emitted an empty mesh.")
    components = loaded.split(only_watertight=False)
    if components:
        loaded = max(components, key=lambda component: float(component.area))
    trimesh.repair.fix_normals(loaded, multibody=False)
    fill_boundary_loops(loaded)
    loaded.remove_unreferenced_vertices()
    final_path = output_dir / "triposr_scaffold.obj"
    loaded.export(final_path)
    report("generative_scaffold_complete")
    return final_path
