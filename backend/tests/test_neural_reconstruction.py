from pathlib import Path

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

import main
import neural_reconstruction as nr


def test_capabilities_report_dual_engines(monkeypatch) -> None:
    monkeypatch.setattr(
        "reconstruction.find_meshroom_batch",
        lambda: Path("C:/fake/meshroom_batch.exe"),
    )
    monkeypatch.setattr(nr, "torch_available", lambda: True)
    monkeypatch.setattr(nr, "vggt_source_available", lambda: False)

    with TestClient(main.app) as client:
        response = client.get("/api/reconstructions/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["meshroom_available"] is True
    assert payload["neural_available"] is True
    assert "auto" in payload["engines"]
    assert "vggt" in payload["engines"]


def test_photo_reconstruction_accepts_engine_choice(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "RECONSTRUCTION_DIR", tmp_path)
    monkeypatch.setattr(main, "_run_reconstruction_job", lambda _: None)
    photos = [
        ("files", (f"photo-{index}.jpg", b"jpeg-data", "image/jpeg"))
        for index in range(6)
    ]

    with TestClient(main.app) as client:
        response = client.post(
            "/api/reconstructions/photos",
            files=photos,
            data={"engine": "vggt"},
        )

    assert response.status_code == 202
    assert response.json()["engine"] == "vggt"


def test_mesh_looks_weak_detects_two_large_components(tmp_path) -> None:
    import numpy as np
    import trimesh

    left = trimesh.creation.box(extents=(10, 10, 20))
    left.apply_translation((-20, 0, 0))
    right = trimesh.creation.box(extents=(10, 10, 20))
    right.apply_translation((20, 0, 0))
    combined = trimesh.util.concatenate([left, right])
    path = tmp_path / "weak.obj"
    combined.export(path)
    assert nr.mesh_looks_weak(path) is True

    solid = trimesh.creation.icosphere(subdivisions=2, radius=5.0)
    solid_path = tmp_path / "solid.obj"
    solid.export(solid_path)
    assert nr.mesh_looks_weak(solid_path) is False


def test_apply_masks_zeros_background(tmp_path) -> None:
    images = tmp_path / "images"
    masks = tmp_path / "masks"
    work = tmp_path / "work"
    images.mkdir()
    masks.mkdir()
    Image.new("RGB", (32, 24), (200, 100, 50)).save(images / "image-0001.jpg")
    mask = Image.new("L", (32, 24), 0)
    for x in range(8, 24):
        for y in range(6, 18):
            mask.putpixel((x, y), 255)
    mask.save(masks / "image-0001.png")

    prepared = nr._apply_masks_inplace(
        [images / "image-0001.jpg"], work, masks
    )
    pixels = list(Image.open(prepared[0]).getdata())
    assert (0, 0, 0) in pixels
    assert (200, 100, 50) in pixels


def test_vggt_stages_full_frames_and_separate_masks(tmp_path) -> None:
    images = tmp_path / "images"
    masks = tmp_path / "masks"
    images.mkdir()
    masks.mkdir()
    source = images / "image-0001.jpg"
    Image.new("RGB", (32, 24), (200, 100, 50)).save(source)
    mask = Image.new("L", (32, 24), 0)
    for x in range(8, 24):
        for y in range(6, 18):
            mask.putpixel((x, y), 255)
    mask.save(masks / "image-0001.png")

    full_frames = nr._stage_full_frame_images([source], tmp_path / "full")
    staged_masks = nr._stage_vggt_masks(
        [source], masks, tmp_path / "mask_inputs"
    )

    full_pixels = np.asarray(Image.open(full_frames[0]).convert("RGB"))
    mask_pixels = np.asarray(Image.open(staged_masks[0]).convert("L"))
    assert np.all(full_pixels == np.array([200, 100, 50]))
    assert mask_pixels.min() == 0
    assert mask_pixels.max() == 255


def test_tsdf_fusion_reconstructs_one_sphere_surface() -> None:
    import numpy as np

    size = 72
    focal = 70.0
    intrinsic = np.array(
        [[focal, 0.0, size / 2], [0.0, focal, size / 2], [0.0, 0.0, 1.0]]
    )
    camera_centers = [
        np.array([0.0, 0.0, 3.0]),
        np.array([0.0, 0.0, -3.0]),
        np.array([3.0, 0.0, 0.0]),
        np.array([-3.0, 0.0, 0.0]),
        np.array([0.0, 3.0, 0.0]),
        np.array([0.0, -3.0, 0.0]),
    ]

    depths = []
    confidences = []
    masks = []
    extrinsics = []
    world_maps = []
    vv, uu = np.meshgrid(np.arange(size), np.arange(size), indexing="ij")
    ray_cam = np.stack(
        ((uu - size / 2) / focal, (vv - size / 2) / focal, np.ones_like(uu)),
        axis=-1,
    )

    for center in camera_centers:
        forward = -center / np.linalg.norm(center)
        up_hint = (
            np.array([0.0, 1.0, 0.0])
            if abs(forward[1]) < 0.9
            else np.array([0.0, 0.0, 1.0])
        )
        right = np.cross(forward, up_hint)
        right /= np.linalg.norm(right)
        down = np.cross(forward, right)
        rotation = np.stack((right, down, forward), axis=0)
        translation = -rotation @ center
        extrinsic = np.column_stack((rotation, translation))

        ray_world = ray_cam @ rotation
        a = np.sum(ray_world * ray_world, axis=-1)
        b = 2.0 * np.sum(center * ray_world, axis=-1)
        c = float(np.dot(center, center) - 1.0)
        discriminant = b * b - 4.0 * a * c
        valid = discriminant >= 0.0
        depth = np.zeros((size, size), dtype=np.float32)
        depth[valid] = (
            (-b[valid] - np.sqrt(discriminant[valid])) / (2.0 * a[valid])
        )
        world = center + ray_world * depth[..., None]
        world[~valid] = 0.0

        depths.append(depth[..., None])
        confidences.append(np.where(valid, 2.0, 0.0))
        masks.append(valid)
        extrinsics.append(extrinsic)
        world_maps.append(world)

    mesh, diagnostics = nr._mesh_from_tsdf(
        np.asarray(depths),
        np.asarray(confidences),
        np.asarray(extrinsics),
        np.repeat(intrinsic[None], len(camera_centers), axis=0),
        np.asarray(world_maps),
        np.asarray(masks),
        resolution=64,
    )

    assert len(mesh.faces) > 500
    assert len(mesh.split(only_watertight=False)) == 1
    assert diagnostics["method"] == "confidence_masked_tsdf"
    assert diagnostics["components_after_cleanup"] == 1
