from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

import numpy as np
import torch
import trimesh
from PIL import Image
from skimage.measure import marching_cubes as skimage_marching_cubes


def _install_torchmcubes_compatibility() -> None:
    """Use scikit-image on Windows instead of compiling torchmcubes."""

    def marching_cubes(volume: torch.Tensor, level: float):
        values = volume.detach().float().cpu().numpy()
        vertices, faces, _, _ = skimage_marching_cubes(
            values, level=level, allow_degenerate=False
        )
        return (
            torch.from_numpy(np.asarray(vertices, dtype=np.float32)),
            torch.from_numpy(np.asarray(faces, dtype=np.int64)),
        )

    compatibility = types.ModuleType("torchmcubes")
    compatibility.marching_cubes = marching_cubes
    sys.modules["torchmcubes"] = compatibility
    # TripoSR's utility module imports rembg even when callers provide an
    # already-masked gray-background image. Avoid the large ONNX dependency.
    rembg_compatibility = types.ModuleType("rembg")
    rembg_compatibility.new_session = lambda *args, **kwargs: None
    rembg_compatibility.remove = lambda image, *args, **kwargs: image
    sys.modules.setdefault("rembg", rembg_compatibility)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="stabilityai/TripoSR")
    parser.add_argument("--resolution", type=int, default=192)
    parser.add_argument("--chunk-size", type=int, default=4096)
    args = parser.parse_args()

    _install_torchmcubes_compatibility()
    sys.path.insert(0, str(args.packages))
    sys.path.insert(0, str(args.source))
    from tsr.system import TSR

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"device={device} resolution={args.resolution}", flush=True)
    model = TSR.from_pretrained(
        args.model,
        config_name="config.yaml",
        weight_name="model.ckpt",
    )
    model.renderer.set_chunk_size(args.chunk_size)
    model.to(device)
    model.eval()

    image = Image.open(args.image).convert("RGB")
    with torch.inference_mode():
        scene_codes = model([image], device=device)
        meshes = model.extract_mesh(
            scene_codes,
            has_vertex_color=True,
            resolution=args.resolution,
        )
    mesh: trimesh.Trimesh = meshes[0]
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(mesh, multibody=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(args.output)
    print(
        f"output={args.output} vertices={len(mesh.vertices)} faces={len(mesh.faces)} "
        f"watertight={mesh.is_watertight}",
        flush=True,
    )


if __name__ == "__main__":
    main()
