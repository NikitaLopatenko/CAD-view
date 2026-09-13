from pathlib import Path

import numpy as np
from PIL import Image

import generative_reconstruction as gr


def _write_frame(
    images: Path,
    masks: Path,
    index: int,
    box: tuple[int, int, int, int],
) -> None:
    Image.new("RGB", (120, 100), (220, 80, 10)).save(
        images / f"image-{index:04d}.jpg"
    )
    mask = Image.new("L", (120, 100), 0)
    for x in range(box[0], box[2]):
        for y in range(box[1], box[3]):
            mask.putpixel((x, y), 255)
    mask.save(masks / f"image-{index:04d}.png")


def test_scaffold_frame_prefers_centered_visible_object(tmp_path) -> None:
    images = tmp_path / "images"
    masks = tmp_path / "masks"
    images.mkdir()
    masks.mkdir()
    _write_frame(images, masks, 1, (0, 10, 45, 90))
    _write_frame(images, masks, 2, (30, 15, 90, 85))

    image, mask, score = gr.select_scaffold_frame(images, masks)

    assert image.name == "image-0002.jpg"
    assert mask is not None and mask.name == "image-0002.png"
    assert score > 0


def test_prepare_scaffold_input_uses_gray_background(tmp_path) -> None:
    images = tmp_path / "images"
    masks = tmp_path / "masks"
    images.mkdir()
    masks.mkdir()
    _write_frame(images, masks, 1, (30, 15, 90, 85))
    output = tmp_path / "prepared.png"

    gr._prepare_scaffold_input(
        images / "image-0001.jpg",
        masks / "image-0001.png",
        output,
    )

    prepared = np.asarray(Image.open(output).convert("RGB"))
    assert prepared.shape == (512, 512, 3)
    np.testing.assert_array_equal(prepared[0, 0], [128, 128, 128])
    assert prepared[..., 0].max() > 200
