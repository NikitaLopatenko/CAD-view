from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from mesh_repair import boundary_edge_count, fill_boundary_loops

RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CAD-View"
VGGT_ROOT = RUNTIME_ROOT / "vggt"
VGGT_REPO = "https://github.com/facebookresearch/vggt.git"
VGGT_MODEL_ID = os.environ.get("CAD_VIEW_VGGT_MODEL", "facebook/VGGT-1B")
MINIMUM_NEURAL_IMAGES = 3
# Cap frames for consumer GPUs (~8 GB). Override with CAD_VIEW_VGGT_MAX_IMAGES.
MAX_NEURAL_IMAGES = int(os.environ.get("CAD_VIEW_VGGT_MAX_IMAGES", "16"))
TSDF_RESOLUTION = int(os.environ.get("CAD_VIEW_TSDF_RESOLUTION", "112"))
TSDF_CONFIDENCE_QUANTILE = float(
    # Keep most masked object pixels. TSDF view fusion suppresses random noise;
    # a high cutoff disproportionately removes glossy white nozzles and caps.
    os.environ.get("CAD_VIEW_TSDF_CONFIDENCE_QUANTILE", "0.35")
)


class NeuralReconstructionError(RuntimeError):
    pass


def _list_images(image_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in image_dir.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
    )


def vggt_source_available() -> bool:
    return (VGGT_ROOT / "vggt" / "models" / "vggt.py").is_file()


def torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def neural_reconstruction_capabilities() -> dict[str, object]:
    torch_ok = torch_available()
    source_ok = vggt_source_available()
    available = torch_ok  # source can be auto-cloned on first run
    return {
        "neural_engine": "vggt",
        "neural_available": available,
        "neural_source_ready": source_ok,
        "neural_model": VGGT_MODEL_ID,
        "neural_minimum_image_count": MINIMUM_NEURAL_IMAGES,
        "neural_runtime_root": str(VGGT_ROOT),
        "neural_requires_torch": not torch_ok,
    }


def ensure_vggt_runtime() -> Path:
    if not torch_available():
        raise NeuralReconstructionError(
            "VGGT neural reconstruction requires PyTorch. "
            'Install with: pip install -e ".[vision]"'
        )

    if vggt_source_available():
        _ensure_vggt_on_path()
        return VGGT_ROOT

    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    if VGGT_ROOT.exists():
        shutil.rmtree(VGGT_ROOT)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", VGGT_REPO, str(VGGT_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not vggt_source_available():
        raise NeuralReconstructionError(
            "Could not install VGGT sources under LocalAppData. "
            f"{(result.stderr or result.stdout or '').strip()[-500:]}"
        )

    # Soft deps used by VGGT; ignore failures if already satisfied.
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "einops",
            "huggingface_hub",
            "safetensors",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    _ensure_vggt_on_path()
    return VGGT_ROOT


def _ensure_vggt_on_path() -> None:
    root = str(VGGT_ROOT.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)


def _subsample_images(paths: list[Path], limit: int = MAX_NEURAL_IMAGES) -> list[Path]:
    if len(paths) <= limit:
        return paths
    if limit == 1:
        return [paths[0]]
    indices = np.linspace(0, len(paths) - 1, num=limit)
    chosen = sorted({int(round(index)) for index in indices})
    return [paths[index] for index in chosen]


def _apply_masks_inplace(
    image_paths: list[Path],
    work_dir: Path,
    mask_dir: Path | None,
) -> list[Path]:
    """Copy images; zero out background when masks exist (VGGT ignores masked pixels)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    prepared: list[Path] = []
    for index, path in enumerate(image_paths):
        # PNG keeps the masked background exactly zero. JPEG ringing around the
        # silhouette otherwise becomes false VGGT geometry.
        destination = work_dir / f"frame-{index:04d}.png"
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            if mask_dir is not None:
                stem_candidates = [
                    mask_dir / f"{path.stem}.png",
                    mask_dir / f"image-{index + 1:04d}.png",
                ]
                mask_path = next((candidate for candidate in stem_candidates if candidate.is_file()), None)
                if mask_path is None:
                    # Fall back to ordered mask files.
                    masks = sorted(mask_dir.glob("*.png"))
                    mask_path = masks[index] if index < len(masks) else None
                if mask_path is not None:
                    with Image.open(mask_path) as mask_image:
                        mask = mask_image.convert("L").resize(rgb.size, Image.Resampling.NEAREST)
                    pixels = np.asarray(rgb).copy()
                    keep = np.asarray(mask) > 127
                    pixels[~keep] = 0
                    rgb = Image.fromarray(pixels)
            rgb.save(destination, format="PNG")
        prepared.append(destination)
    return prepared


def _stage_full_frame_images(
    image_paths: list[Path],
    work_dir: Path,
) -> list[Path]:
    """Stage lossless full frames; VGGT needs scene texture for pose and depth."""
    work_dir.mkdir(parents=True, exist_ok=True)
    prepared: list[Path] = []
    for index, path in enumerate(image_paths):
        destination = work_dir / f"frame-{index:04d}.png"
        with Image.open(path) as image:
            image.convert("RGB").save(destination, format="PNG")
        prepared.append(destination)
    return prepared


def _matching_mask_path(
    image_path: Path,
    mask_dir: Path,
    index: int,
) -> Path | None:
    candidates = [
        mask_dir / f"{image_path.stem}.png",
        mask_dir / f"image-{index + 1:04d}.png",
    ]
    match = next((candidate for candidate in candidates if candidate.is_file()), None)
    if match is not None:
        return match
    masks = sorted(mask_dir.glob("*.png"))
    return masks[index] if index < len(masks) else None


def _stage_vggt_masks(
    image_paths: list[Path],
    mask_dir: Path,
    work_dir: Path,
) -> list[Path]:
    """
    Stage masks independently from images.

    They pass through the same VGGT resize/crop function, but are not shown to
    the network. They are consumed only by confidence filtering and TSDF fusion.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    prepared: list[Path] = []
    for index, image_path in enumerate(image_paths):
        mask_path = _matching_mask_path(image_path, mask_dir, index)
        if mask_path is None:
            raise NeuralReconstructionError(
                f"No foreground mask matches {image_path.name}."
            )
        destination = work_dir / f"mask-{index:04d}.png"
        with Image.open(mask_path) as opened:
            opened.convert("L").save(destination, format="PNG")
        prepared.append(destination)
    return prepared


def _model_foreground_masks(mask_images: object) -> np.ndarray:
    """Convert preprocessed RGB mask tensors to boolean model-space masks."""
    if hasattr(mask_images, "detach"):
        values = mask_images.detach().float().cpu().numpy()
    else:
        values = np.asarray(mask_images, dtype=np.float32)
    if values.ndim == 5:
        values = values[0]
    if values.ndim != 4 or values.shape[1] != 3:
        raise NeuralReconstructionError("Unexpected VGGT mask tensor shape.")
    return np.max(values, axis=1) >= 0.5


def _clean_surface_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Keep the dominant reconstructed skin and repair basic mesh defects."""
    mesh.remove_unreferenced_vertices()
    if len(mesh.faces) < 20:
        raise NeuralReconstructionError("Surface reconstruction produced too few faces.")

    try:
        components = mesh.split(only_watertight=False)
    except Exception:
        components = []
    if components:
        mesh = max(components, key=lambda component: float(component.area))

    try:
        trimesh.smoothing.filter_taubin(mesh, lamb=0.45, nu=-0.47, iterations=8)
    except Exception:
        pass
    try:
        trimesh.repair.fix_normals(mesh, multibody=False)
        trimesh.repair.fill_holes(mesh)
        # Trimesh's conservative helper only fills triangular/quad openings.
        # TSDF crop boundaries are often larger simple loops.
        fill_boundary_loops(mesh)
    except Exception:
        pass
    mesh.remove_unreferenced_vertices()
    return mesh


def _robust_object_bounds(
    world_points: np.ndarray,
    confidences: np.ndarray,
    foreground_masks: np.ndarray,
    *,
    confidence_quantile: float = TSDF_CONFIDENCE_QUANTILE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Find an outlier-resistant object volume from masked depth pointmaps."""
    points = np.asarray(world_points, dtype=np.float64)
    conf = np.asarray(confidences, dtype=np.float64)
    masks = np.asarray(foreground_masks, dtype=bool)
    if points.shape[:-1] != conf.shape or conf.shape != masks.shape:
        raise NeuralReconstructionError("VGGT depth, confidence, and mask shapes differ.")

    valid = (
        masks
        & np.isfinite(conf)
        & np.isfinite(points).all(axis=-1)
        & (np.linalg.norm(points, axis=-1) > 1e-8)
    )
    if int(valid.sum()) < 500:
        raise NeuralReconstructionError(
            "VGGT produced too few finite object-depth samples for TSDF fusion."
        )

    # Bounds use every finite masked point with robust coordinate quantiles.
    # Confidence is applied during fusion; using it here can crop away an
    # entire low-confidence material region (for example a translucent nozzle).
    selected = points[valid]
    threshold = float(np.quantile(conf[valid], confidence_quantile))
    trusted = valid & (conf >= threshold)

    lower = np.quantile(selected, 0.01, axis=0)
    upper = np.quantile(selected, 0.99, axis=0)
    extent = np.maximum(upper - lower, 1e-6)
    padding = np.maximum(extent * 0.10, np.max(extent) * 0.03)
    return lower - padding, upper + padding, trusted


def _mesh_from_tsdf(
    depth_maps: np.ndarray,
    depth_confidences: np.ndarray,
    extrinsics: np.ndarray,
    intrinsics: np.ndarray,
    world_points_from_depth: np.ndarray,
    foreground_masks: np.ndarray,
    *,
    resolution: int = TSDF_RESOLUTION,
    confidence_quantile: float = TSDF_CONFIDENCE_QUANTILE,
) -> tuple[trimesh.Trimesh, dict[str, object]]:
    """
    Fuse VGGT depth maps into a confidence- and mask-weighted TSDF.

    Unlike raw occupied voxels, a TSDF averages signed surface evidence across
    views, suppressing isolated pointmap outliers before marching cubes.
    """
    from skimage.measure import marching_cubes

    depths = np.asarray(depth_maps, dtype=np.float32)
    confidences = np.asarray(depth_confidences, dtype=np.float32)
    cameras = np.asarray(extrinsics, dtype=np.float64)
    calibration = np.asarray(intrinsics, dtype=np.float64)
    masks = np.asarray(foreground_masks, dtype=bool)
    if depths.ndim == 4 and depths.shape[-1] == 1:
        depths = depths[..., 0]
    if confidences.ndim == 4 and confidences.shape[-1] == 1:
        confidences = confidences[..., 0]
    if not (
        depths.shape == confidences.shape == masks.shape
        and cameras.shape == (depths.shape[0], 3, 4)
        and calibration.shape == (depths.shape[0], 3, 3)
    ):
        raise NeuralReconstructionError("Unexpected VGGT TSDF input shapes.")

    lower, upper, trusted = _robust_object_bounds(
        world_points_from_depth,
        confidences,
        masks,
        confidence_quantile=confidence_quantile,
    )
    longest = float(np.max(upper - lower))
    resolution = max(48, min(int(resolution), 160))
    voxel_size = longest / float(resolution - 1)
    dimensions = np.maximum(
        16, np.ceil((upper - lower) / voxel_size).astype(np.int64) + 1
    )
    axes = [
        lower[axis] + np.arange(int(dimensions[axis]), dtype=np.float64) * voxel_size
        for axis in range(3)
    ]
    xx, yy, zz = np.meshgrid(*axes, indexing="ij")
    voxels = np.stack((xx, yy, zz), axis=-1).reshape(-1, 3)
    del xx, yy, zz

    tsdf_sum = np.zeros(len(voxels), dtype=np.float32)
    weight_sum = np.zeros(len(voxels), dtype=np.float32)
    truncation = voxel_size * 5.0
    frame_thresholds = [
        float(np.quantile(confidences[index][trusted[index]], confidence_quantile))
        if np.any(trusted[index])
        else float("inf")
        for index in range(len(depths))
    ]

    chunk_size = 250_000
    for frame_index in range(len(depths)):
        depth = depths[frame_index]
        confidence = confidences[frame_index]
        foreground = masks[frame_index]
        height, width = depth.shape
        rotation = cameras[frame_index, :, :3]
        translation = cameras[frame_index, :, 3]
        intrinsic = calibration[frame_index]
        threshold = frame_thresholds[frame_index]

        for start in range(0, len(voxels), chunk_size):
            stop = min(start + chunk_size, len(voxels))
            world = voxels[start:stop]
            camera_points = world @ rotation.T + translation
            z = camera_points[:, 2]
            positive = z > 1e-8
            safe_z = np.where(positive, z, 1.0)
            u = np.rint(intrinsic[0, 0] * camera_points[:, 0] / safe_z + intrinsic[0, 2]).astype(np.int64)
            v = np.rint(intrinsic[1, 1] * camera_points[:, 1] / safe_z + intrinsic[1, 2]).astype(np.int64)
            inside = positive & (u >= 0) & (u < width) & (v >= 0) & (v < height)
            if not np.any(inside):
                continue

            local_indices = np.flatnonzero(inside)
            sample_u = u[inside]
            sample_v = v[inside]
            observed_depth = depth[sample_v, sample_u]
            observed_conf = confidence[sample_v, sample_u]
            observed_mask = foreground[sample_v, sample_u]
            signed_distance = observed_depth - z[inside]
            valid = (
                observed_mask
                & np.isfinite(observed_depth)
                & np.isfinite(observed_conf)
                & (observed_depth > 1e-8)
                & (observed_conf >= threshold)
                & (signed_distance >= -truncation)
            )
            if not np.any(valid):
                continue

            local_indices = local_indices[valid]
            normalized = np.clip(signed_distance[valid] / truncation, -1.0, 1.0)
            # Confidence weights are normalized per frame to prevent one view
            # from dominating solely because its head has a different scale.
            weights = np.clip(observed_conf[valid] / max(threshold, 1e-6), 1.0, 4.0)
            target = slice(start, stop)
            chunk_tsdf = tsdf_sum[target]
            chunk_weights = weight_sum[target]
            chunk_tsdf[local_indices] += normalized.astype(np.float32) * weights.astype(np.float32)
            chunk_weights[local_indices] += weights.astype(np.float32)

    observed = weight_sum > 0
    if int(observed.sum()) < 1_000:
        raise NeuralReconstructionError(
            "Too few TSDF voxels received consistent masked depth observations."
        )
    field = np.ones(len(voxels), dtype=np.float32)
    field[observed] = tsdf_sum[observed] / weight_sum[observed]
    field = field.reshape(tuple(int(value) for value in dimensions))
    if not (float(field.min()) < 0.0 < float(field.max())):
        raise NeuralReconstructionError(
            "VGGT TSDF has no stable zero crossing; refusing to emit another blob."
        )

    # Marching Cubes emits an open boundary when a negative TSDF region reaches
    # the robust crop box. A positive guard band makes the inference explicit
    # and keeps the observed surface away from the extraction volume boundary.
    guard_voxels = 2
    field = np.pad(field, guard_voxels, mode="constant", constant_values=1.0)
    lower = lower - guard_voxels * voxel_size
    vertices, faces, _, _ = marching_cubes(
        field,
        level=0.0,
        spacing=(voxel_size, voxel_size, voxel_size),
        allow_degenerate=False,
    )
    vertices += lower
    mesh = _clean_surface_mesh(
        trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    )
    diagnostics: dict[str, object] = {
        "method": "confidence_masked_tsdf",
        "resolution": [int(value) for value in dimensions],
        "voxel_size": voxel_size,
        "truncation": truncation,
        "observed_voxels": int(observed.sum()),
        "input_depth_samples": int(trusted.sum()),
        "components_after_cleanup": len(mesh.split(only_watertight=False)),
        "boundary_edges_after_cleanup": boundary_edge_count(mesh),
        "volume_guard_voxels": guard_voxels,
        "watertight": bool(mesh.is_watertight),
    }
    return mesh, diagnostics


def _mesh_from_points(points: np.ndarray, pitch: float | None = None) -> trimesh.Trimesh:
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 50:
        raise NeuralReconstructionError(
            "VGGT produced too few 3D points to build a surface mesh."
        )

    # Cap point count for voxelization.
    if len(points) > 400_000:
        choice = np.random.default_rng(0).choice(len(points), size=400_000, replace=False)
        points = points[choice]

    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    extents = np.maximum(maxs - mins, 1e-6)
    if pitch is None:
        pitch = float(np.max(extents) / 96.0)
    pitch = max(pitch, float(np.max(extents) / 192.0), 1e-5)

    indices = np.floor((points - mins) / pitch).astype(np.int64)
    shape = tuple(int(value) + 1 for value in indices.max(axis=0))
    while int(np.prod(shape)) > 96**3:
        pitch *= 1.25
        indices = np.floor((points - mins) / pitch).astype(np.int64)
        shape = tuple(int(value) + 1 for value in indices.max(axis=0))

    occupancy = np.zeros(shape, dtype=bool)
    occupancy[indices[:, 0], indices[:, 1], indices[:, 2]] = True

    try:
        mesh = trimesh.voxel.ops.matrix_to_marching_cubes(
            matrix=occupancy, pitch=pitch
        )
        mesh.apply_translation(mins)
    except ImportError:
        # scikit-image is optional; convex hull still yields an inspectable surface.
        cloud = trimesh.points.PointCloud(points)
        mesh = cloud.convex_hull

    return _clean_surface_mesh(mesh)


def run_vggt_reconstruction(
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

    report("neural_preparing_frames")
    ensure_vggt_runtime()

    import torch
    from vggt.models.vggt import VGGT
    from vggt.utils.load_fn import load_and_preprocess_images

    image_paths = _list_images(image_dir)
    if len(image_paths) < MINIMUM_NEURAL_IMAGES:
        raise NeuralReconstructionError(
            f"VGGT needs at least {MINIMUM_NEURAL_IMAGES} images "
            f"(received {len(image_paths)})."
        )

    selected = _subsample_images(image_paths, MAX_NEURAL_IMAGES)
    work_images = output_dir / "vggt_inputs"
    if work_images.exists():
        shutil.rmtree(work_images)
    # Full scene is always passed to VGGT. Masking the network input destroys
    # the carpet/grid features needed for pose, just like masking classical SfM.
    prepared = _stage_full_frame_images(selected, work_images)
    prepared_masks: list[Path] | None = None
    if mask_dir is not None:
        mask_inputs = output_dir / "vggt_masks"
        if mask_inputs.exists():
            shutil.rmtree(mask_inputs)
        prepared_masks = _stage_vggt_masks(selected, mask_dir, mask_inputs)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = (
        torch.bfloat16
        if device == "cuda" and torch.cuda.get_device_capability()[0] >= 8
        else torch.float16
        if device == "cuda"
        else torch.float32
    )

    log_chunks = [
        f"VGGT reconstruction on {len(prepared)} of {len(image_paths)} frames "
        f"(cap={MAX_NEURAL_IMAGES})",
        f"device={device} dtype={dtype} model={VGGT_MODEL_ID}",
    ]

    report(f"neural_loading_model_{len(prepared)}_frames")
    model = VGGT.from_pretrained(VGGT_MODEL_ID).to(device)
    model.eval()
    images = load_and_preprocess_images([str(path) for path in prepared]).to(device)
    mask_images = (
        load_and_preprocess_images([str(path) for path in prepared_masks])
        if prepared_masks is not None
        else None
    )

    report(f"neural_inferring_{len(prepared)}_frames")
    with torch.no_grad():
        if device == "cuda":
            with torch.cuda.amp.autocast(dtype=dtype):
                predictions = model(images)
        else:
            predictions = model(images)

    report("neural_fusing_tsdf")
    if (
        "depth" not in predictions
        or "depth_conf" not in predictions
        or "pose_enc" not in predictions
    ):
        raise NeuralReconstructionError(
            "VGGT did not return depth, confidence, and camera predictions."
        )

    from vggt.utils.geometry import unproject_depth_map_to_point_map
    from vggt.utils.pose_enc import pose_encoding_to_extri_intri

    depth_tensor = predictions["depth"]
    confidence_tensor = predictions["depth_conf"]
    extrinsic_tensor, intrinsic_tensor = pose_encoding_to_extri_intri(
        predictions["pose_enc"], images.shape[-2:]
    )
    depth_np = depth_tensor.detach().float().cpu().numpy()
    confidence_np = confidence_tensor.detach().float().cpu().numpy()
    extrinsic_np = extrinsic_tensor.detach().float().cpu().numpy()
    intrinsic_np = intrinsic_tensor.detach().float().cpu().numpy()
    if depth_np.ndim == 5:
        depth_np = depth_np[0]
    if confidence_np.ndim == 4:
        confidence_np = confidence_np[0]
    if extrinsic_np.ndim == 4:
        extrinsic_np = extrinsic_np[0]
    if intrinsic_np.ndim == 4:
        intrinsic_np = intrinsic_np[0]
    world_from_depth = unproject_depth_map_to_point_map(
        depth_np,
        extrinsic_np,
        intrinsic_np,
    )
    foreground_masks = (
        _model_foreground_masks(mask_images)
        if mask_images is not None
        else np.ones(confidence_np.shape, dtype=bool)
    )

    finite = np.isfinite(world_from_depth).all(axis=-1)
    valid_cloud = foreground_masks & finite & (depth_np[..., 0] > 1e-8)
    threshold = float(
        np.quantile(confidence_np[valid_cloud], TSDF_CONFIDENCE_QUANTILE)
    )
    valid_cloud &= confidence_np >= threshold
    points_np = world_from_depth[valid_cloud]

    output_dir.mkdir(parents=True, exist_ok=True)
    cloud_path = output_dir / "vggt_points.ply"
    trimesh.points.PointCloud(points_np).export(cloud_path)

    mesh, diagnostics = _mesh_from_tsdf(
        depth_np,
        confidence_np,
        extrinsic_np,
        intrinsic_np,
        world_from_depth,
        foreground_masks,
    )
    mesh_path = output_dir / "vggt_mesh.obj"
    mesh.export(mesh_path)

    log_chunks.extend(
        [
            f"points={len(points_np)} faces={len(mesh.faces)}",
            f"meshing={diagnostics}",
        ]
    )
    if log_path is not None:
        log_path.write_text("\n".join(log_chunks), encoding="utf-8")
    report("neural_complete")
    # Reconstruction jobs are infrequent and other local 3D models share this
    # consumer GPU. Release VGGT tensors/cache instead of pinning ~8 GB.
    del (
        model,
        predictions,
        images,
        mask_images,
        depth_tensor,
        confidence_tensor,
        extrinsic_tensor,
        intrinsic_tensor,
    )
    if device == "cuda":
        torch.cuda.empty_cache()
    return mesh_path


def mesh_looks_weak(mesh_path: Path) -> bool:
    """Heuristic quality gate for Meshroom outputs that 'succeed' but are unusable."""
    try:
        loaded = trimesh.load(mesh_path, force="mesh")
    except Exception:
        return True
    if isinstance(loaded, trimesh.Scene):
        loaded = trimesh.util.concatenate(
            [geometry for geometry in loaded.geometry.values() if isinstance(geometry, trimesh.Trimesh)]
        )
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) < 200:
        return True
    try:
        components = loaded.split(only_watertight=False)
    except Exception:
        return False
    if len(components) < 2:
        return False
    areas = sorted((float(component.area) for component in components), reverse=True)
    return len(areas) >= 2 and areas[1] > 0.2 * max(areas[0], 1e-9)
