from __future__ import annotations

import importlib.util
import threading
from dataclasses import dataclass
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw

SegmentationMode = Literal["sam2", "rectangle_fallback"]
MODEL_ID = "facebook/sam2.1-hiera-small"


@dataclass(frozen=True)
class NormalizedBox:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def pixels(self, width: int, height: int) -> list[float]:
        return [
            self.x_min * width,
            self.y_min * height,
            self.x_max * width,
            self.y_max * height,
        ]


_model = None
_processor = None
_device = None
_model_lock = threading.Lock()


def sam2_dependencies_available() -> bool:
    return (
        importlib.util.find_spec("torch") is not None
        and importlib.util.find_spec("transformers") is not None
    )


def segmentation_capabilities() -> dict[str, object]:
    available = sam2_dependencies_available()
    return {
        "segmentation_available": available,
        "segmentation_engine": "sam2" if available else "rectangle_fallback",
        "segmentation_model": MODEL_ID if available else None,
    }


def _load_sam2():
    global _device, _model, _processor
    if _model is not None and _processor is not None:
        return _model, _processor, _device

    with _model_lock:
        if _model is not None and _processor is not None:
            return _model, _processor, _device

        import torch
        from transformers import Sam2Model, Sam2Processor

        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float16 if _device.type == "cuda" else torch.float32
        _processor = Sam2Processor.from_pretrained(MODEL_ID)
        _model = Sam2Model.from_pretrained(MODEL_ID, torch_dtype=dtype)
        _model.to(_device)
        _model.eval()
        return _model, _processor, _device


def _rectangle_mask(image: Image.Image, box: NormalizedBox) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle(box.pixels(*image.size), fill=255)
    return mask


def segment_with_box(
    image: Image.Image, box: NormalizedBox
) -> tuple[Image.Image, SegmentationMode]:
    image = image.convert("RGB")
    if not sam2_dependencies_available():
        return _rectangle_mask(image, box), "rectangle_fallback"

    try:
        import torch

        model, processor, device = _load_sam2()
        inputs = processor(
            images=image,
            input_boxes=[[box.pixels(*image.size)]],
            return_tensors="pt",
        ).to(device)
        with torch.inference_mode():
            outputs = model(**inputs, multimask_output=False)
        masks = processor.post_process_masks(
            outputs.pred_masks.cpu(),
            inputs["original_sizes"].cpu(),
        )[0]
        mask_array = np.asarray(masks[0, 0]) > 0
        mask = Image.fromarray(mask_array.astype(np.uint8) * 255, mode="L")
        return mask, "sam2"
    except Exception:
        # The UI reports this mode, so a failed model load is never presented as AI output.
        return _rectangle_mask(image, box), "rectangle_fallback"
