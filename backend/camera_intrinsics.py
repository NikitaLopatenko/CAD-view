from __future__ import annotations

import math
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image
from PIL.ExifTags import Base


FULL_FRAME_WIDTH_MM = 36.0
# Typical modern phone main-camera horizontal FOV when EXIF was stripped
# (Telegram / WhatsApp / gallery exports). Better than Meshroom's 45° default.
PHONE_DEFAULT_HORIZONTAL_FOV_DEG = 69.0


@dataclass(frozen=True)
class CameraIntrinsicEstimate:
    make: str | None
    model: str | None
    focal_length_mm: float | None
    focal_length_35mm: float | None
    sensor_width_mm: float | None
    image_width: int | None
    image_height: int | None
    horizontal_fov_deg: float | None
    source: str
    shared_intrinsic_recommended: bool
    notes: list[str]

    def report(self) -> dict[str, object]:
        return asdict(self)


def find_camera_sensors_db() -> Path | None:
    configured = Path(os.environ.get("ALICEVISION_SENSOR_DB", "")).expanduser()
    if configured.is_file():
        return configured

    runtime = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        / "CAD-View"
        / "Meshroom"
        / "aliceVision"
        / "share"
        / "aliceVision"
        / "cameraSensors.db"
    )
    if runtime.is_file():
        return runtime

    project_db = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "Meshroom-2023.3.0"
        / "aliceVision"
        / "share"
        / "aliceVision"
        / "cameraSensors.db"
    )
    return project_db if project_db.is_file() else None


def _rational_to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, tuple) and len(value) == 2 and value[1]:
        return float(value[0]) / float(value[1])
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        denominator = float(value.denominator)
        if denominator == 0:
            return None
        return float(value.numerator) / denominator
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _normalize_token(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def lookup_sensor_width_mm(make: str | None, model: str | None) -> float | None:
    database = find_camera_sensors_db()
    if database is None or not make or not model:
        return None

    make_key = _normalize_token(make)
    model_key = _normalize_token(model)
    best: tuple[int, float] | None = None
    for line in database.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 3:
            continue
        db_make, db_model, sensor = parts[0], parts[1], parts[2]
        if _normalize_token(db_make) != make_key:
            continue
        db_model_key = _normalize_token(db_model)
        if model_key == db_model_key:
            score = 1000
        elif model_key and model_key in db_model_key:
            score = len(model_key)
        elif db_model_key and db_model_key in model_key:
            score = len(db_model_key)
        else:
            continue
        try:
            width = float(sensor)
        except ValueError:
            continue
        if best is None or score > best[0]:
            best = (score, width)
    return None if best is None else best[1]


def horizontal_fov_degrees(
    *,
    focal_length_mm: float | None = None,
    sensor_width_mm: float | None = None,
    focal_length_35mm: float | None = None,
) -> float | None:
    if focal_length_35mm and focal_length_35mm > 0:
        return math.degrees(
            2.0 * math.atan(FULL_FRAME_WIDTH_MM / (2.0 * focal_length_35mm))
        )
    if (
        focal_length_mm
        and sensor_width_mm
        and focal_length_mm > 0
        and sensor_width_mm > 0
    ):
        return math.degrees(
            2.0 * math.atan(sensor_width_mm / (2.0 * focal_length_mm))
        )
    return None


def focal_length_35mm_from_horizontal_fov(fov_deg: float) -> float:
    half = math.radians(fov_deg) / 2.0
    return FULL_FRAME_WIDTH_MM / (2.0 * math.tan(half))


def read_image_exif(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        width, height = image.size
        raw = image.getexif()
    make = raw.get(Base.Make)
    model = raw.get(Base.Model)
    focal = _rational_to_float(raw.get(Base.FocalLength))
    focal_35 = raw.get(Base.FocalLengthIn35mmFilm)
    focal_35_mm = float(focal_35) if isinstance(focal_35, (int, float)) else None
    return {
        "make": str(make).strip() if make else None,
        "model": str(model).strip() if model else None,
        "focal_length_mm": focal,
        "focal_length_35mm": focal_35_mm,
        "image_width": width,
        "image_height": height,
    }


def probe_video_camera_tags(video_path: Path) -> dict[str, str | None]:
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(video_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    text = f"{result.stdout}\n{result.stderr}"
    make_match = re.search(r"(?:com\.apple\.quicktime\.)?make\s*[:=]\s*(.+)", text, re.I)
    model_match = re.search(
        r"(?:com\.apple\.quicktime\.)?model\s*[:=]\s*(.+)", text, re.I
    )
    return {
        "make": make_match.group(1).strip() if make_match else None,
        "model": model_match.group(1).strip() if model_match else None,
    }


def stamp_shared_exif(
    image_paths: list[Path],
    *,
    make: str | None,
    model: str | None,
    focal_length_mm: float | None,
    focal_length_35mm: float | None,
) -> int:
    stamped = 0
    for path in image_paths:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            exif = image.getexif()
            if make:
                exif[Base.Make] = make
            if model:
                exif[Base.Model] = model
            if focal_length_mm:
                scale = 1000
                exif[Base.FocalLength] = (
                    int(round(focal_length_mm * scale)),
                    scale,
                )
            if focal_length_35mm:
                exif[Base.FocalLengthIn35mmFilm] = int(round(focal_length_35mm))
            rgb.save(path, format="JPEG", quality=95, exif=exif)
            stamped += 1
    return stamped


def estimate_intrinsics_from_images(image_dir: Path) -> CameraIntrinsicEstimate:
    images = sorted(
        [
            path
            for path in image_dir.iterdir()
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
        ]
    )
    notes: list[str] = []
    if not images:
        return CameraIntrinsicEstimate(
            make=None,
            model=None,
            focal_length_mm=None,
            focal_length_35mm=None,
            sensor_width_mm=None,
            image_width=None,
            image_height=None,
            horizontal_fov_deg=None,
            source="none",
            shared_intrinsic_recommended=True,
            notes=["No images available for EXIF inspection."],
        )

    samples = [read_image_exif(path) for path in images[: min(12, len(images))]]
    makes = {sample["make"] for sample in samples if sample["make"]}
    models = {sample["model"] for sample in samples if sample["model"]}
    focals = [
        sample["focal_length_mm"]
        for sample in samples
        if isinstance(sample["focal_length_mm"], float)
    ]
    focals_35 = [
        sample["focal_length_35mm"]
        for sample in samples
        if isinstance(sample["focal_length_35mm"], (int, float))
    ]

    make = next(iter(makes)) if len(makes) == 1 else None
    model = next(iter(models)) if len(models) == 1 else None
    if len(makes) > 1 or len(models) > 1:
        notes.append(
            "Multiple camera identities were found; a shared intrinsic is still "
            "recommended for one continuous capture session."
        )

    focal = sum(focals) / len(focals) if focals else None
    focal_35 = (
        sum(float(value) for value in focals_35) / len(focals_35) if focals_35 else None
    )
    sensor_width = lookup_sensor_width_mm(
        make if isinstance(make, str) else None,
        model if isinstance(model, str) else None,
    )
    if make and model and sensor_width is None:
        notes.append(
            f"No sensor-width match for {make} {model} in AliceVision cameraSensors.db."
        )
    fov = horizontal_fov_degrees(
        focal_length_mm=focal,
        sensor_width_mm=sensor_width,
        focal_length_35mm=focal_35,
    )
    if fov is None:
        fov = PHONE_DEFAULT_HORIZONTAL_FOV_DEG
        focal_35 = focal_length_35mm_from_horizontal_fov(fov)
        notes.append(
            "No usable EXIF focal length; applying a shared phone-camera FOV "
            f"fallback of {PHONE_DEFAULT_HORIZONTAL_FOV_DEG:.0f}° so CameraInit "
            "does not use Meshroom's overly narrow 45° default."
        )
        source = "phone_default"
    else:
        notes.append(
            "Derived a shared horizontal field-of-view for CameraInit to reduce "
            "shape warping across the capture."
        )
        source = "exif"

    if not (make or model or focal or focal_35) and source != "phone_default":
        source = "missing_exif"
        notes.append(
            "Frames have no usable camera EXIF. For video, CAD-View will try to "
            "recover make/model from the source container and stamp shared EXIF."
        )

    first = samples[0]
    return CameraIntrinsicEstimate(
        make=make if isinstance(make, str) else None,
        model=model if isinstance(model, str) else None,
        focal_length_mm=focal,
        focal_length_35mm=focal_35,
        sensor_width_mm=sensor_width,
        image_width=first.get("image_width")
        if isinstance(first.get("image_width"), int)
        else None,
        image_height=first.get("image_height")
        if isinstance(first.get("image_height"), int)
        else None,
        horizontal_fov_deg=fov,
        source=source,
        shared_intrinsic_recommended=True,
        notes=notes,
    )


def prepare_shared_camera_model(
    image_dir: Path,
    *,
    video_path: Path | None = None,
) -> CameraIntrinsicEstimate:
    estimate = estimate_intrinsics_from_images(image_dir)
    notes = list(estimate.notes)
    make = estimate.make
    model = estimate.model
    focal = estimate.focal_length_mm
    focal_35 = estimate.focal_length_35mm
    source = estimate.source

    if video_path is not None and (make is None or model is None):
        tags = probe_video_camera_tags(video_path)
        make = make or tags.get("make")
        model = model or tags.get("model")
        if tags.get("make") or tags.get("model"):
            source = "video_container"
            notes.append(
                "Recovered camera identity from the video container and stamped it "
                "onto extracted frames."
            )

    sensor_width = estimate.sensor_width_mm or lookup_sensor_width_mm(make, model)
    fov = horizontal_fov_degrees(
        focal_length_mm=focal,
        sensor_width_mm=sensor_width,
        focal_length_35mm=focal_35,
    )
    if fov is None:
        fov = PHONE_DEFAULT_HORIZONTAL_FOV_DEG
        focal_35 = focal_length_35mm_from_horizontal_fov(fov)
        source = "phone_default"
        notes.append(
            f"Applied phone FOV fallback ({PHONE_DEFAULT_HORIZONTAL_FOV_DEG:.0f}°) "
            "and stamped a synthetic 35mm-equivalent focal length onto frames."
        )
    elif focal_35 is None:
        focal_35 = focal_length_35mm_from_horizontal_fov(fov)

    image_paths = sorted(
        path
        for path in image_dir.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg"}
    )
    if make or model or focal or focal_35:
        stamped = stamp_shared_exif(
            image_paths,
            make=make,
            model=model,
            focal_length_mm=focal,
            focal_length_35mm=focal_35,
        )
        notes.append(f"Stamped shared EXIF onto {stamped} JPEG frames.")

    return CameraIntrinsicEstimate(
        make=make,
        model=model,
        focal_length_mm=focal,
        focal_length_35mm=focal_35,
        sensor_width_mm=sensor_width,
        image_width=estimate.image_width,
        image_height=estimate.image_height,
        horizontal_fov_deg=fov,
        source=source,
        shared_intrinsic_recommended=True,
        notes=notes,
    )
