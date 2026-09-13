from __future__ import annotations

import hashlib
import json
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

import numpy as np
import trimesh
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from camera_intrinsics import prepare_shared_camera_model
from generative_reconstruction import (
    generative_reconstruction_capabilities,
    run_triposr_reconstruction,
)
from mesh_repair import (
    MeshRepairError,
    create_watertight_proxy,
    fill_boundary_loops,
)
from neural_reconstruction import (
    mesh_looks_weak,
    neural_reconstruction_capabilities,
    run_vggt_reconstruction,
)
from parametric_reconstruction import (
    ParametricReconstructionError,
    build_solidworks_part,
    solidworks_available,
    write_solidworks_builder_script,
)
from recipe_selection import build_recipe
from primitive_fitting import analyze_primitives, export_mesh_shape_step, export_step
from reconstruction import (
    MINIMUM_IMAGE_COUNT,
    ReconstructionError,
    extract_video_frames,
    reconstruction_capabilities,
    run_meshroom,
)
from segmentation import (
    NormalizedBox,
    segmentation_capabilities,
    segment_with_box,
)

APP_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = APP_DIR / "uploads"
RECONSTRUCTION_DIR = APP_DIR / "reconstructions"
EXPORT_DIR = APP_DIR / "exports"
SUPPORTED_EXTENSIONS = {".stl", ".obj", ".ply"}
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_RECONSTRUCTION_INPUT_BYTES = 2 * 1024 * 1024 * 1024
LengthUnit = Literal["mm", "cm", "m", "in"]
Point3 = tuple[float, float, float]


class Bounds(BaseModel):
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]


class Qualification(BaseModel):
    vertex_count: int
    face_count: int
    connected_components: int
    is_watertight: bool
    is_winding_consistent: bool
    euler_number: int
    bounds: Bounds
    extents: tuple[float, float, float]
    volume: float | None = Field(
        description="Signed mesh volume in source units cubed; null when not watertight."
    )


class Provenance(BaseModel):
    source_kind: Literal[
        "mesh_upload", "photogrammetry", "neural_reconstruction", "derived"
    ]
    original_filename: str
    sha256: str
    byte_size: int
    imported_at: datetime
    geometry_state: Literal["observed", "reconstructed", "scaled", "repaired"]
    parent_id: UUID | None = None
    processing_steps: list[str]


class ScaleRequest(BaseModel):
    point_a: Point3
    point_b: Point3
    target_distance: float = Field(gt=0)
    unit: LengthUnit


class DeclareUnitsRequest(BaseModel):
    """Assign working units without changing geometry (scale factor = 1)."""

    unit: LengthUnit


class ScaleApplication(BaseModel):
    point_a: Point3
    point_b: Point3
    measured_distance_source: float
    target_distance: float
    unit: LengthUnit
    scale_factor: float
    residual: float


class RepairRequest(BaseModel):
    fill_small_holes: bool = False
    mode: Literal["conservative", "watertight_proxy"] = "conservative"
    voxel_resolution: int = Field(default=160, ge=64, le=320)
    closing_radius_voxels: int = Field(default=2, ge=0, le=8)
    smoothing_iterations: int = Field(default=6, ge=0, le=30)


class RepairReport(BaseModel):
    before: Qualification
    after: Qualification
    duplicate_faces_removed: int
    faces_added: int
    winding_reoriented: bool
    fill_small_holes_requested: bool
    net_surface_area_change: float
    max_existing_vertex_displacement: float
    requires_human_review: bool
    method: Literal["conservative", "voxel_wrap"] = "conservative"
    boundary_loops_filled: int = 0
    voxel_resolution: int | None = None
    voxel_pitch: float | None = None
    closing_radius_voxels: int | None = None
    smoothing_iterations: int | None = None
    rms_deviation: float | None = None
    p95_deviation: float | None = None
    max_deviation: float | None = None
    normalized_rms_percent: float | None = None


class CheckConstraintRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    point_a: Point3
    point_b: Point3
    expected_distance: float = Field(gt=0)
    tolerance: float = Field(ge=0)


class CheckConstraint(BaseModel):
    id: UUID
    label: str
    point_a: Point3
    point_b: Point3
    measured_distance: float
    expected_distance: float
    tolerance: float
    unit: LengthUnit
    residual: float
    relative_error_percent: float
    passes: bool
    checked_at: datetime


class CameraIntrinsicReport(BaseModel):
    make: str | None = None
    model: str | None = None
    focal_length_mm: float | None = None
    focal_length_35mm: float | None = None
    sensor_width_mm: float | None = None
    image_width: int | None = None
    image_height: int | None = None
    horizontal_fov_deg: float | None = None
    source: str = "none"
    shared_intrinsic_recommended: bool = True
    notes: list[str] = []


class ReconstructionJob(BaseModel):
    id: UUID
    engine: Literal["auto", "meshroom", "vggt", "triposr"]
    resolved_engine: Literal["meshroom", "vggt", "triposr"] | None = None
    input_kind: Literal["photo_set", "video"]
    status: Literal["queued", "running", "succeeded", "failed"]
    stage: str
    input_count: int
    output_mesh_id: UUID | None = None
    camera: CameraIntrinsicReport | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class NormalizedBoxRequest(BaseModel):
    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)

    def as_box(self) -> NormalizedBox:
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("The foreground box must have positive width and height.")
        return NormalizedBox(**self.model_dump())


class PrimitiveFitReport(BaseModel):
    primitive_type: Literal["box", "cylinder", "mesh_solid"]
    parameters: dict[str, object]
    rms_deviation: float
    max_deviation: float
    normalized_rms: float


class PrimitiveAnalysis(BaseModel):
    mesh_id: UUID
    unit: LengthUnit | None
    fits: list[PrimitiveFitReport]


class PrimitiveExportRequest(BaseModel):
    primitive_type: Literal["box", "cylinder"]
    max_normalized_rms: float = Field(default=0.02, gt=0, le=0.25)


class StepExportRecord(BaseModel):
    id: UUID
    source_mesh_id: UUID
    primitive_type: Literal["box", "cylinder", "mesh_solid"]
    unit: LengthUnit
    fit: PrimitiveFitReport
    download_url: str
    generated_at: datetime


class ParametricRecipeReport(BaseModel):
    mesh_id: UUID
    unit: LengthUnit
    strategy: str
    confidence: float = Field(ge=0, le=1)
    features: list[dict[str, object]]
    diagnostics: dict[str, object]
    warnings: list[str]
    solidworks_available: bool


class SolidWorksExportRequest(BaseModel):
    visible: bool = False
    allow_approximate: bool = False


class SolidWorksExportRecord(BaseModel):
    id: UUID
    source_mesh_id: UUID
    strategy: str
    confidence: float
    feature_count: int
    unit: LengthUnit
    artifact_type: Literal["sldprt", "builder_script"]
    download_url: str
    generated_at: datetime
    warnings: list[str]


class MeshRecord(BaseModel):
    id: UUID
    extension: Literal[".stl", ".obj", ".ply"]
    download_url: str
    unit: LengthUnit | None = None
    qualification: Qualification
    provenance: Provenance
    scale_application: ScaleApplication | None = None
    repair_report: RepairReport | None = None
    check_constraints: list[CheckConstraint] = Field(default_factory=list)


@asynccontextmanager
async def lifespan(_: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    RECONSTRUCTION_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="CAD-View Geometry API",
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "Ingests an immutable observed mesh and reports topology without "
        "silently changing physical geometry."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _paths(mesh_id: UUID, extension: str) -> tuple[Path, Path]:
    return (
        UPLOAD_DIR / f"{mesh_id}{extension}",
        UPLOAD_DIR / f"{mesh_id}.json",
    )


def _load_mesh(path: Path) -> trimesh.Trimesh:
    try:
        # Processing welds coincident STL vertices for valid topology analysis.
        # The uploaded source bytes remain immutable on disk.
        loaded = trimesh.load(path, force="mesh", process=True)
    except Exception as exc:
        raise ValueError(f"Mesh parser rejected the file: {exc}") from exc

    if isinstance(loaded, trimesh.Scene):
        if not loaded.geometry:
            raise ValueError("The uploaded scene contains no mesh geometry.")
        loaded = loaded.to_mesh()

    if not isinstance(loaded, trimesh.Trimesh) or loaded.is_empty:
        raise ValueError("The uploaded file contains no triangle mesh.")
    if len(loaded.vertices) == 0 or len(loaded.faces) == 0:
        raise ValueError("The uploaded mesh must contain vertices and faces.")
    return loaded


def _vector(values: np.ndarray) -> tuple[float, float, float]:
    return tuple(float(value) for value in values)


def _connected_component_count(
    face_count: int, adjacency: np.ndarray
) -> int:
    parents = list(range(face_count))

    def find(face: int) -> int:
        while parents[face] != face:
            parents[face] = parents[parents[face]]
            face = parents[face]
        return face

    for left, right in adjacency:
        left_root = find(int(left))
        right_root = find(int(right))
        if left_root != right_root:
            parents[right_root] = left_root

    return len({find(face) for face in range(face_count)})


def qualify_mesh(mesh: trimesh.Trimesh) -> Qualification:
    volume = float(mesh.volume) if mesh.is_watertight else None
    return Qualification(
        vertex_count=int(len(mesh.vertices)),
        face_count=int(len(mesh.faces)),
        connected_components=_connected_component_count(
            len(mesh.faces), mesh.face_adjacency
        ),
        is_watertight=bool(mesh.is_watertight),
        is_winding_consistent=bool(mesh.is_winding_consistent),
        euler_number=int(mesh.euler_number),
        bounds=Bounds(
            minimum=_vector(mesh.bounds[0]),
            maximum=_vector(mesh.bounds[1]),
        ),
        extents=_vector(mesh.extents),
        volume=volume,
    )


def _load_record(mesh_id: UUID) -> tuple[MeshRecord, Path]:
    metadata_path = UPLOAD_DIR / f"{mesh_id}.json"
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Mesh not found.")

    try:
        record = MeshRecord.model_validate_json(metadata_path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500, detail="Stored mesh metadata is unreadable."
        ) from exc

    mesh_path, _ = _paths(mesh_id, record.extension)
    if not mesh_path.exists():
        raise HTTPException(status_code=404, detail="Mesh file not found.")
    return record, mesh_path


def _hash_file(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    byte_size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            hasher.update(chunk)
            byte_size += len(chunk)
    return hasher.hexdigest(), byte_size


def _job_paths(job_id: UUID) -> tuple[Path, Path]:
    job_dir = RECONSTRUCTION_DIR / str(job_id)
    return job_dir, job_dir / "job.json"


def _save_job(job: ReconstructionJob) -> None:
    job_dir, metadata_path = _job_paths(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)
    job.updated_at = datetime.now(timezone.utc)
    metadata_path.write_text(
        json.dumps(job.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


def _update_job_stage(job_id: UUID, stage: str) -> None:
    job = _load_job(job_id)
    job.stage = stage
    if job.status == "queued":
        job.status = "running"
    _save_job(job)


def _load_job(job_id: UUID) -> ReconstructionJob:
    _, metadata_path = _job_paths(job_id)
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Reconstruction job not found.")
    try:
        return ReconstructionJob.model_validate_json(
            metadata_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500, detail="Reconstruction job metadata is unreadable."
        ) from exc


def _publish_reconstruction_mesh(
    job: ReconstructionJob, generated_path: Path
) -> MeshRecord:
    extension = generated_path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ReconstructionError(
            f"Reconstruction generated unsupported mesh type: {extension}."
        )

    mesh_id = uuid4()
    mesh_path, metadata_path = _paths(mesh_id, extension)
    shutil.copyfile(generated_path, mesh_path)
    sha256, byte_size = _hash_file(mesh_path)
    mesh = _load_mesh(mesh_path)
    job_dir, _ = _job_paths(job.id)
    resolved = job.resolved_engine or "meshroom"
    if resolved in {"vggt", "triposr"}:
        processing_steps = [
            "vggt_neural_reconstruction"
            if resolved == "vggt"
            else "triposr_single_image_scaffold"
        ]
        source_kind: Literal[
            "mesh_upload", "photogrammetry", "neural_reconstruction", "derived"
        ] = "neural_reconstruction"
    else:
        processing_steps = ["meshroom_photogrammetry"]
        source_kind = "photogrammetry"
    if (job_dir / "masks").is_dir():
        processing_steps.insert(0, "foreground_masking")
    record = MeshRecord(
        id=mesh_id,
        extension=extension,
        download_url=f"/api/meshes/{mesh_id}/file",
        unit=None,
        qualification=qualify_mesh(mesh),
        provenance=Provenance(
            source_kind=source_kind,
            original_filename=f"reconstruction-{job.id}{extension}",
            sha256=sha256,
            byte_size=byte_size,
            imported_at=datetime.now(timezone.utc),
            geometry_state="reconstructed",
            parent_id=None,
            processing_steps=processing_steps,
        ),
        scale_application=None,
        repair_report=None,
        check_constraints=[],
    )
    metadata_path.write_text(
        json.dumps(record.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    return record


def _resolve_reconstruction_engine(
    requested: Literal["auto", "meshroom", "vggt", "triposr"],
) -> Literal["meshroom", "vggt", "triposr"]:
    caps = (
        reconstruction_capabilities()
        | neural_reconstruction_capabilities()
        | generative_reconstruction_capabilities()
    )
    meshroom_ok = bool(caps.get("meshroom_available") or caps.get("executable"))
    neural_ok = bool(caps.get("neural_available"))
    if requested == "meshroom":
        if not meshroom_ok:
            raise ReconstructionError("Meshroom is not installed.")
        return "meshroom"
    if requested == "vggt":
        if not neural_ok:
            raise ReconstructionError(
                "VGGT neural engine requires PyTorch. Install vision extras."
            )
        return "vggt"
    if requested == "triposr":
        if not caps.get("generative_available"):
            raise ReconstructionError(
                "TripoSR requires PyTorch and the vision dependencies."
            )
        return "triposr"
    # auto: classical full-frame SfM first; neural rescues weak/empty dense meshing.
    if meshroom_ok:
        return "meshroom"
    if neural_ok:
        return "vggt"
    raise ReconstructionError("No reconstruction engine is available.")


def _run_reconstruction_job(job_id: UUID) -> None:
    job = _load_job(job_id)
    job_dir, _ = _job_paths(job_id)
    image_dir = job_dir / "images"
    mask_dir = job_dir / "masks"
    output_dir = job_dir / "output"
    log_path = job_dir / "meshroom.log"
    neural_log = job_dir / "vggt.log"
    try:
        job.status = "running"
        video_path: Path | None = None
        if job.input_kind == "video":
            job.stage = "extracting_video_frames"
            _save_job(job)
            video_path = next((job_dir / "video").iterdir())
            frames = extract_video_frames(video_path, image_dir)
            job.input_count = len(frames)

        job.stage = "camera_intrinsics"
        _save_job(job)
        camera = prepare_shared_camera_model(image_dir, video_path=video_path)
        job.camera = CameraIntrinsicReport(**camera.report())
        _save_job(job)

        primary = _resolve_reconstruction_engine(job.engine)
        job.resolved_engine = primary
        _save_job(job)

        generated_path: Path | None = None
        errors: list[str] = []

        caps = reconstruction_capabilities()
        if job.engine == "auto":
            engines_to_try: list[Literal["meshroom", "vggt", "triposr"]] = []
            if caps.get("meshroom_available"):
                engines_to_try.append("meshroom")
            if caps.get("neural_available"):
                engines_to_try.append("vggt")
            if not engines_to_try:
                engines_to_try = [primary]
        elif job.engine == "meshroom":
            # Classical first; automatically rescue with VGGT when dense MVS fails.
            engines_to_try = ["meshroom"]
            if caps.get("neural_available"):
                engines_to_try.append("vggt")
        else:
            engines_to_try = [primary]

        for engine_name in engines_to_try:
            job.resolved_engine = engine_name
            try:
                if engine_name == "meshroom":
                    job.stage = "photogrammetry"
                    _save_job(job)
                    candidate = run_meshroom(
                        image_dir,
                        output_dir,
                        log_path,
                        job_id=str(job_id),
                        mask_dir=mask_dir if mask_dir.is_dir() else None,
                        default_field_of_view=camera.horizontal_fov_deg,
                    )
                    remaining = engines_to_try[
                        engines_to_try.index(engine_name) + 1 :
                    ]
                    if (
                        "vggt" in remaining
                        and mesh_looks_weak(candidate)
                    ):
                        errors.append(
                            "Meshroom produced a fragmented/weak mesh; "
                            "trying VGGT neural reconstruction."
                        )
                        continue
                    generated_path = candidate
                    break
                if engine_name == "vggt":
                    job.stage = "neural_reconstruction"
                    _save_job(job)
                    if errors and job.engine in {"auto", "meshroom"}:
                        # Preserve why classical densification handed off.
                        job.error = " | ".join(errors)[-500:]
                        _save_job(job)
                    generated_path = run_vggt_reconstruction(
                        image_dir,
                        output_dir / "vggt",
                        mask_dir=mask_dir if mask_dir.is_dir() else None,
                        log_path=neural_log,
                        progress=lambda stage: _update_job_stage(job_id, stage),
                    )
                else:
                    job.stage = "generative_scaffold"
                    _save_job(job)
                    generated_path = run_triposr_reconstruction(
                        image_dir,
                        output_dir / "triposr",
                        mask_dir=mask_dir if mask_dir.is_dir() else None,
                        log_path=job_dir / "triposr.log",
                        progress=lambda stage: _update_job_stage(job_id, stage),
                    )
                break
            except Exception as engine_error:
                errors.append(f"{engine_name}: {engine_error}")
                if engine_name == engines_to_try[-1]:
                    raise
                continue

        if generated_path is None:
            raise ReconstructionError(
                "All reconstruction engines failed. " + " | ".join(errors)[-900:]
            )

        job.stage = "qualifying_output"
        _save_job(job)
        record = _publish_reconstruction_mesh(job, generated_path)
        job.status = "succeeded"
        job.stage = "complete"
        job.output_mesh_id = record.id
        job.error = None
        _save_job(job)
    except Exception as exc:
        job.status = "failed"
        job.stage = "failed"
        job.error = str(exc)[:1000]
        _save_job(job)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/reconstructions/capabilities")
def get_reconstruction_capabilities() -> dict[str, object]:
    return reconstruction_capabilities() | segmentation_capabilities()


@app.post("/api/reconstructions/mask-preview")
def create_mask_preview(
    file: Annotated[UploadFile, File(...)],
    box: Annotated[str, Form(...)],
) -> Response:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Mask previews support JPG, PNG, and TIFF files.",
        )
    try:
        request = NormalizedBoxRequest.model_validate_json(box)
        normalized_box = request.as_box()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    file.file.close()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Preview image exceeds 100 MB.")
    try:
        with Image.open(BytesIO(data)) as opened:
            opened.load()
            mask, mode = segment_with_box(opened, normalized_box)
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=422, detail="The uploaded image is unreadable.") from exc

    output = BytesIO()
    mask.save(output, format="PNG")
    return Response(
        content=output.getvalue(),
        media_type="image/png",
        headers={"X-Segmentation-Mode": mode},
    )


@app.post(
    "/api/reconstructions/photos",
    response_model=ReconstructionJob,
    status_code=202,
)
def create_photo_reconstruction(
    background_tasks: BackgroundTasks,
    files: Annotated[list[UploadFile], File(...)],
    masks: Annotated[list[UploadFile] | None, File()] = None,
    engine: Annotated[
        Literal["auto", "meshroom", "vggt", "triposr"], Form()
    ] = "auto",
) -> ReconstructionJob:
    if len(files) < MINIMUM_IMAGE_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"Upload at least {MINIMUM_IMAGE_COUNT} overlapping photographs.",
        )
    extensions = [Path(file.filename or "").suffix.lower() for file in files]
    if any(extension not in SUPPORTED_IMAGE_EXTENSIONS for extension in extensions):
        raise HTTPException(
            status_code=415,
            detail="Photo sets support JPG, PNG, and TIFF files.",
        )
    if masks is not None and len(masks) != len(files):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one reviewed foreground mask per photograph.",
        )

    now = datetime.now(timezone.utc)
    job = ReconstructionJob(
        id=uuid4(),
        engine=engine,
        input_kind="photo_set",
        status="queued",
        stage="storing_inputs",
        input_count=len(files),
        created_at=now,
        updated_at=now,
    )
    job_dir, _ = _job_paths(job.id)
    image_dir = job_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=False)
    mask_dir = job_dir / "masks"
    if masks is not None:
        mask_dir.mkdir()
    total_bytes = 0
    try:
        for index, (file, extension) in enumerate(zip(files, extensions), start=1):
            output_path = image_dir / f"image-{index:04d}{extension}"
            with output_path.open("xb") as destination:
                while chunk := file.file.read(1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_RECONSTRUCTION_INPUT_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail="Reconstruction inputs exceed the 2 GB limit.",
                        )
                    destination.write(chunk)
        if masks is not None:
            for index, mask_file in enumerate(masks, start=1):
                mask_data = mask_file.file.read(MAX_UPLOAD_BYTES + 1)
                if len(mask_data) > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="A foreground mask exceeds the 100 MB limit.",
                    )
                image_path = next(image_dir.glob(f"image-{index:04d}.*"))
                try:
                    with Image.open(image_path) as source_image:
                        source_size = source_image.size
                    with Image.open(BytesIO(mask_data)) as opened_mask:
                        opened_mask.load()
                        if opened_mask.size != source_size:
                            raise HTTPException(
                                status_code=422,
                                detail=(
                                    f"Mask {index} dimensions do not match its photograph."
                                ),
                            )
                        opened_mask.convert("L").save(
                            mask_dir / f"image-{index:04d}.png",
                            format="PNG",
                        )
                except (UnidentifiedImageError, OSError) as exc:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Foreground mask {index} is unreadable.",
                    ) from exc
        job.stage = "queued"
        _save_job(job)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    finally:
        for file in files:
            file.file.close()
        for mask_file in masks or []:
            mask_file.file.close()

    background_tasks.add_task(_run_reconstruction_job, job.id)
    return job


@app.post(
    "/api/reconstructions/video",
    response_model=ReconstructionJob,
    status_code=202,
)
def create_video_reconstruction(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    engine: Annotated[
        Literal["auto", "meshroom", "vggt", "triposr"], Form()
    ] = "auto",
) -> ReconstructionJob:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in SUPPORTED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Video reconstruction supports MP4, MOV, AVI, MKV, and WebM.",
        )

    now = datetime.now(timezone.utc)
    job = ReconstructionJob(
        id=uuid4(),
        engine=engine,
        input_kind="video",
        status="queued",
        stage="storing_input",
        input_count=0,
        created_at=now,
        updated_at=now,
    )
    job_dir, _ = _job_paths(job.id)
    video_dir = job_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=False)
    video_path = video_dir / f"source{extension}"
    byte_size = 0
    try:
        with video_path.open("xb") as destination:
            while chunk := file.file.read(1024 * 1024):
                byte_size += len(chunk)
                if byte_size > MAX_RECONSTRUCTION_INPUT_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Video exceeds the 2 GB input limit.",
                    )
                destination.write(chunk)
        job.stage = "queued"
        _save_job(job)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    finally:
        file.file.close()

    background_tasks.add_task(_run_reconstruction_job, job.id)
    return job


@app.get("/api/reconstructions/{job_id}", response_model=ReconstructionJob)
def get_reconstruction_job(job_id: UUID) -> ReconstructionJob:
    return _load_job(job_id)


@app.post("/api/meshes", response_model=MeshRecord, status_code=201)
def upload_mesh(file: Annotated[UploadFile, File(...)]) -> MeshRecord:
    original_filename = Path(file.filename or "").name
    extension = Path(original_filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported mesh type. Upload one of: {supported}.",
        )

    mesh_id = uuid4()
    mesh_path, metadata_path = _paths(mesh_id, extension)
    hasher = hashlib.sha256()
    byte_size = 0

    try:
        with mesh_path.open("xb") as destination:
            while chunk := file.file.read(1024 * 1024):
                byte_size += len(chunk)
                if byte_size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413, detail="Mesh exceeds the 100 MB upload limit."
                    )
                destination.write(chunk)
                hasher.update(chunk)

        mesh = _load_mesh(mesh_path)
        record = MeshRecord(
            id=mesh_id,
            extension=extension,
            download_url=f"/api/meshes/{mesh_id}/file",
            unit=None,
            qualification=qualify_mesh(mesh),
            provenance=Provenance(
                source_kind="mesh_upload",
                original_filename=original_filename,
                sha256=hasher.hexdigest(),
                byte_size=byte_size,
                imported_at=datetime.now(timezone.utc),
                geometry_state="observed",
                parent_id=None,
                processing_steps=[],
            ),
            scale_application=None,
            repair_report=None,
            check_constraints=[],
        )
        metadata_path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        return record
    except HTTPException:
        mesh_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise
    except (OSError, ValueError) as exc:
        mesh_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        file.file.close()


@app.get("/api/meshes", response_model=list[MeshRecord])
def list_meshes(limit: int = 40) -> list[MeshRecord]:
    capped = max(1, min(limit, 100))
    records: list[MeshRecord] = []
    for metadata_path in UPLOAD_DIR.glob("*.json"):
        try:
            record = MeshRecord.model_validate_json(
                metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            continue
        mesh_path, _ = _paths(record.id, record.extension)
        if mesh_path.exists():
            records.append(record)
    records.sort(key=lambda item: item.provenance.imported_at, reverse=True)
    return records[:capped]


@app.get("/api/exports", response_model=list[StepExportRecord])
def list_exports(limit: int = 40) -> list[StepExportRecord]:
    capped = max(1, min(limit, 100))
    records: list[StepExportRecord] = []
    for metadata_path in EXPORT_DIR.glob("*.json"):
        try:
            record = StepExportRecord.model_validate_json(
                metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            continue
        step_path = EXPORT_DIR / f"{record.id}.step"
        if step_path.exists():
            records.append(record)
    records.sort(key=lambda item: item.generated_at, reverse=True)
    return records[:capped]


@app.get("/api/meshes/{mesh_id}", response_model=MeshRecord)
def get_mesh(mesh_id: UUID) -> MeshRecord:
    record, _ = _load_record(mesh_id)
    return record


@app.post(
    "/api/meshes/{mesh_id}/checks",
    response_model=MeshRecord,
    status_code=201,
)
def add_check_constraint(
    mesh_id: UUID, request: CheckConstraintRequest
) -> MeshRecord:
    record, _ = _load_record(mesh_id)
    label = request.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="Check label cannot be blank.")
    if record.unit is None:
        raise HTTPException(
            status_code=409,
            detail="Apply a scale constraint before adding physical check dimensions.",
        )

    point_a = np.asarray(request.point_a, dtype=np.float64)
    point_b = np.asarray(request.point_b, dtype=np.float64)
    measured_distance = float(np.linalg.norm(point_b - point_a))
    if not np.isfinite(measured_distance) or measured_distance <= 1e-12:
        raise HTTPException(
            status_code=422,
            detail="Check points must be distinct finite coordinates.",
        )

    residual = measured_distance - request.expected_distance
    check = CheckConstraint(
        id=uuid4(),
        label=label,
        point_a=request.point_a,
        point_b=request.point_b,
        measured_distance=measured_distance,
        expected_distance=request.expected_distance,
        tolerance=request.tolerance,
        unit=record.unit,
        residual=residual,
        relative_error_percent=abs(residual) / request.expected_distance * 100.0,
        passes=abs(residual) <= request.tolerance,
        checked_at=datetime.now(timezone.utc),
    )
    record.check_constraints.append(check)
    metadata_path = UPLOAD_DIR / f"{mesh_id}.json"
    try:
        metadata_path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail="Could not store dimensional check."
        ) from exc
    return record


@app.post("/api/meshes/{mesh_id}/units", response_model=MeshRecord, status_code=201)
def declare_mesh_units(mesh_id: UUID, request: DeclareUnitsRequest) -> MeshRecord:
    """Assign working CAD units without changing vertex coordinates."""
    source_record, source_path = _load_record(mesh_id)
    if source_record.unit == request.unit and "declare_units" in (
        source_record.provenance.processing_steps
    ):
        return source_record

    mesh_id_out = uuid4()
    mesh_path, metadata_path = _paths(mesh_id_out, source_record.extension)
    try:
        shutil.copyfile(source_path, mesh_path)
        sha256, byte_size = _hash_file(mesh_path)
        mesh = _load_mesh(mesh_path)
        stem = Path(source_record.provenance.original_filename).stem
        record = MeshRecord(
            id=mesh_id_out,
            extension=source_record.extension,
            download_url=f"/api/meshes/{mesh_id_out}/file",
            unit=request.unit,
            qualification=qualify_mesh(mesh),
            provenance=Provenance(
                source_kind="derived",
                original_filename=f"{stem}-units-{request.unit}{source_record.extension}",
                sha256=sha256,
                byte_size=byte_size,
                imported_at=datetime.now(timezone.utc),
                geometry_state=source_record.provenance.geometry_state,
                parent_id=source_record.id,
                processing_steps=["declare_units"],
            ),
            scale_application=None,
            repair_report=None,
            check_constraints=[],
        )
        metadata_path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        return record
    except Exception as exc:
        mesh_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500, detail="Could not store unit-declared mesh."
        ) from exc


@app.post("/api/meshes/{mesh_id}/scale", response_model=MeshRecord, status_code=201)
def scale_mesh(mesh_id: UUID, request: ScaleRequest) -> MeshRecord:
    source_record, source_path = _load_record(mesh_id)
    source_mesh = _load_mesh(source_path)
    point_a = np.asarray(request.point_a, dtype=np.float64)
    point_b = np.asarray(request.point_b, dtype=np.float64)
    source_distance = float(np.linalg.norm(point_b - point_a))
    if not np.isfinite(source_distance) or source_distance <= 1e-12:
        raise HTTPException(
            status_code=422,
            detail="Scale anchor points must be distinct finite coordinates.",
        )

    scale_factor = request.target_distance / source_distance
    if not np.isfinite(scale_factor):
        raise HTTPException(status_code=422, detail="Scale factor is not finite.")

    scaled_mesh = source_mesh.copy()
    scaled_mesh.apply_scale(scale_factor)
    derived_id = uuid4()
    derived_path, metadata_path = _paths(derived_id, ".stl")
    exported = scaled_mesh.export(file_type="stl")
    if not isinstance(exported, bytes):
        raise HTTPException(status_code=500, detail="Could not export scaled mesh.")

    scaled_distance = float(
        np.linalg.norm((point_b * scale_factor) - (point_a * scale_factor))
    )
    application = ScaleApplication(
        point_a=request.point_a,
        point_b=request.point_b,
        measured_distance_source=source_distance,
        target_distance=request.target_distance,
        unit=request.unit,
        scale_factor=scale_factor,
        residual=abs(scaled_distance - request.target_distance),
    )
    output_name = f"{Path(source_record.provenance.original_filename).stem}-scaled.stl"
    record = MeshRecord(
        id=derived_id,
        extension=".stl",
        download_url=f"/api/meshes/{derived_id}/file",
        unit=request.unit,
        qualification=qualify_mesh(scaled_mesh),
        provenance=Provenance(
            source_kind="derived",
            original_filename=output_name,
            sha256=hashlib.sha256(exported).hexdigest(),
            byte_size=len(exported),
            imported_at=datetime.now(timezone.utc),
            geometry_state="scaled",
            parent_id=mesh_id,
            processing_steps=["uniform_scale"],
        ),
        scale_application=application,
        repair_report=None,
        check_constraints=[],
    )

    try:
        with derived_path.open("xb") as destination:
            destination.write(exported)
        metadata_path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
    except OSError as exc:
        derived_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500, detail="Could not store scaled mesh."
        ) from exc

    return record


@app.post("/api/meshes/{mesh_id}/repair", response_model=MeshRecord, status_code=201)
def repair_mesh(mesh_id: UUID, request: RepairRequest) -> MeshRecord:
    source_record, source_path = _load_record(mesh_id)
    source_mesh = _load_mesh(source_path)
    working_mesh = source_mesh.copy()
    before = qualify_mesh(source_mesh)
    surface_area_before = float(source_mesh.area)
    steps: list[str] = []

    unique_faces = working_mesh.unique_faces()
    duplicate_faces_removed = int(len(working_mesh.faces) - np.count_nonzero(unique_faces))
    if duplicate_faces_removed:
        working_mesh.update_faces(unique_faces)
        steps.append("remove_duplicate_faces")

    winding_before = bool(working_mesh.is_winding_consistent)
    trimesh.repair.fix_normals(working_mesh, multibody=True)
    winding_reoriented = winding_before != bool(working_mesh.is_winding_consistent)
    if winding_reoriented:
        steps.append("fix_winding")

    faces_before_fill = len(working_mesh.faces)
    boundary_loops_filled = 0
    if request.mode == "conservative" and request.fill_small_holes:
        trimesh.repair.fill_holes(working_mesh)
        boundary_fill = fill_boundary_loops(working_mesh)
        boundary_loops_filled = boundary_fill.loops_filled
    faces_added = int(max(0, len(working_mesh.faces) - faces_before_fill))
    if faces_added:
        steps.append("fill_boundary_loops")

    proxy_diagnostics = None
    if request.mode == "watertight_proxy":
        try:
            working_mesh, proxy_diagnostics = create_watertight_proxy(
                working_mesh,
                resolution=request.voxel_resolution,
                closing_radius_voxels=request.closing_radius_voxels,
                smoothing_iterations=request.smoothing_iterations,
            )
        except MeshRepairError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        boundary_loops_filled = proxy_diagnostics.boundary_loops_filled
        faces_added = int(max(0, len(working_mesh.faces) - faces_before_fill))
        steps.extend(
            [
                "watertight_voxel_wrap",
                f"closing_radius_{proxy_diagnostics.closing_radius_voxels}_voxels",
                f"taubin_smooth_{proxy_diagnostics.smoothing_iterations}_iterations",
            ]
        )

    working_mesh.remove_unreferenced_vertices()
    after = qualify_mesh(working_mesh)
    surface_area_after = float(working_mesh.area)
    report = RepairReport(
        before=before,
        after=after,
        duplicate_faces_removed=duplicate_faces_removed,
        faces_added=faces_added,
        winding_reoriented=winding_reoriented,
        fill_small_holes_requested=request.fill_small_holes,
        net_surface_area_change=surface_area_after - surface_area_before,
        max_existing_vertex_displacement=(
            proxy_diagnostics.max_deviation if proxy_diagnostics else 0.0
        ),
        requires_human_review=faces_added > 0 or proxy_diagnostics is not None,
        method=proxy_diagnostics.method if proxy_diagnostics else "conservative",
        boundary_loops_filled=boundary_loops_filled,
        voxel_resolution=(
            proxy_diagnostics.voxel_resolution if proxy_diagnostics else None
        ),
        voxel_pitch=proxy_diagnostics.voxel_pitch if proxy_diagnostics else None,
        closing_radius_voxels=(
            proxy_diagnostics.closing_radius_voxels if proxy_diagnostics else None
        ),
        smoothing_iterations=(
            proxy_diagnostics.smoothing_iterations if proxy_diagnostics else None
        ),
        rms_deviation=proxy_diagnostics.rms_deviation if proxy_diagnostics else None,
        p95_deviation=proxy_diagnostics.p95_deviation if proxy_diagnostics else None,
        max_deviation=proxy_diagnostics.max_deviation if proxy_diagnostics else None,
        normalized_rms_percent=(
            proxy_diagnostics.normalized_rms_percent if proxy_diagnostics else None
        ),
    )

    derived_id = uuid4()
    derived_path, metadata_path = _paths(derived_id, ".stl")
    exported = working_mesh.export(file_type="stl")
    if not isinstance(exported, bytes):
        raise HTTPException(status_code=500, detail="Could not export repaired mesh.")

    suffix = "watertight-proxy" if request.mode == "watertight_proxy" else "repaired"
    output_name = f"{Path(source_record.provenance.original_filename).stem}-{suffix}.stl"
    record = MeshRecord(
        id=derived_id,
        extension=".stl",
        download_url=f"/api/meshes/{derived_id}/file",
        unit=source_record.unit,
        qualification=after,
        provenance=Provenance(
            source_kind="derived",
            original_filename=output_name,
            sha256=hashlib.sha256(exported).hexdigest(),
            byte_size=len(exported),
            imported_at=datetime.now(timezone.utc),
            geometry_state="repaired",
            parent_id=mesh_id,
            processing_steps=steps,
        ),
        scale_application=source_record.scale_application,
        repair_report=report,
        check_constraints=source_record.check_constraints,
    )

    try:
        with derived_path.open("xb") as destination:
            destination.write(exported)
        metadata_path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
    except OSError as exc:
        derived_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500, detail="Could not store repaired mesh."
        ) from exc

    return record


@app.get(
    "/api/meshes/{mesh_id}/primitives",
    response_model=PrimitiveAnalysis,
)
def analyze_mesh_primitives(mesh_id: UUID) -> PrimitiveAnalysis:
    record, mesh_path = _load_record(mesh_id)
    mesh = _load_mesh(mesh_path)
    fits = [
        PrimitiveFitReport.model_validate(candidate.report())
        for candidate in analyze_primitives(mesh)
    ]
    return PrimitiveAnalysis(mesh_id=mesh_id, unit=record.unit, fits=fits)


def _parametric_recipe_for_mesh(
    mesh_id: UUID,
) -> tuple[MeshRecord, dict[str, object]]:
    record, mesh_path = _load_record(mesh_id)
    if record.unit is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Declare working units or apply a physical scale before "
                "recovering parametric CAD features."
            ),
        )
    try:
        recipe = build_recipe(_load_mesh(mesh_path), record.unit)
    except ParametricReconstructionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record, recipe


@app.get(
    "/api/meshes/{mesh_id}/parametric",
    response_model=ParametricRecipeReport,
)
def analyze_parametric_recipe(mesh_id: UUID) -> ParametricRecipeReport:
    record, recipe = _parametric_recipe_for_mesh(mesh_id)
    return ParametricRecipeReport(
        mesh_id=record.id,
        unit=record.unit,
        strategy=str(recipe["strategy"]),
        confidence=float(recipe["confidence"]),
        features=list(recipe["features"]),
        diagnostics=dict(recipe["diagnostics"]),
        warnings=list(recipe["warnings"]),
        solidworks_available=solidworks_available(),
    )


@app.post(
    "/api/meshes/{mesh_id}/solidworks",
    response_model=SolidWorksExportRecord,
    status_code=201,
)
def export_solidworks_feature_part(
    mesh_id: UUID,
    request: SolidWorksExportRequest,
) -> SolidWorksExportRecord:
    record, recipe = _parametric_recipe_for_mesh(mesh_id)
    quality = recipe.get("diagnostics", {}).get("quality", {})
    if (
        not bool(quality.get("export_recommended", True))
        and not request.allow_approximate
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Native CAD export was blocked because the best recovered "
                f"feature tree has agreement {float(recipe['confidence']):.3f}, "
                f"below the required {float(quality.get('minimum_export_agreement', 0.60)):.2f}. "
                "Use the mesh STEP fallback or explicitly set "
                "allow_approximate=true."
            ),
        )
    export_id = uuid4()
    directory = EXPORT_DIR / "solidworks"
    part_path = directory / f"{export_id}.SLDPRT"
    script_path = directory / f"{export_id}.vbs"
    metadata_path = directory / f"{export_id}.json"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        export_warnings = list(recipe["warnings"])
        artifact_type: Literal["sldprt", "builder_script"] = "sldprt"
        try:
            build_solidworks_part(recipe, part_path, visible=request.visible)
        except ParametricReconstructionError as exc:
            part_path.unlink(missing_ok=True)
            write_solidworks_builder_script(recipe, script_path)
            artifact_type = "builder_script"
            export_warnings.append(
                "Server-side SolidWorks automation could not enter an interactive "
                "sketch session. Download and double-click the builder script; it "
                "creates CADView-editable.SLDPRT beside itself. "
                f"Direct automation detail: {exc}"
            )
        exported = SolidWorksExportRecord(
            id=export_id,
            source_mesh_id=record.id,
            strategy=str(recipe["strategy"]),
            confidence=float(recipe["confidence"]),
            feature_count=len(recipe["features"]),
            unit=record.unit,
            artifact_type=artifact_type,
            download_url=f"/api/solidworks-exports/{export_id}/file",
            generated_at=datetime.now(timezone.utc),
            warnings=export_warnings,
        )
        metadata_path.write_text(
            json.dumps(exported.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        return exported
    except ParametricReconstructionError as exc:
        part_path.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        part_path.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=f"SolidWorks feature-tree export failed: {exc}",
        ) from exc


@app.get("/api/solidworks-exports/{export_id}/file")
def download_solidworks_export(export_id: UUID) -> FileResponse:
    directory = EXPORT_DIR / "solidworks"
    metadata_path = directory / f"{export_id}.json"
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="SolidWorks export not found.")
    record = SolidWorksExportRecord.model_validate_json(
        metadata_path.read_text(encoding="utf-8")
    )
    if record.artifact_type == "sldprt":
        artifact_path = directory / f"{export_id}.SLDPRT"
        filename = f"parametric-{record.source_mesh_id}.SLDPRT"
        media_type = "application/octet-stream"
    else:
        artifact_path = directory / f"{export_id}.vbs"
        filename = f"build-parametric-{record.source_mesh_id}.vbs"
        media_type = "text/vbscript"
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="SolidWorks artifact not found.")
    return FileResponse(
        artifact_path,
        filename=filename,
        media_type=media_type,
    )


@app.post(
    "/api/meshes/{mesh_id}/step",
    response_model=StepExportRecord,
    status_code=201,
)
def export_mesh_step(
    mesh_id: UUID, request: PrimitiveExportRequest
) -> StepExportRecord:
    source_record, mesh_path = _load_record(mesh_id)
    if source_record.unit is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Declare working units or apply a physical scale before "
                "exporting analytic STEP."
            ),
        )

    mesh = _load_mesh(mesh_path)
    candidate = next(
        candidate
        for candidate in analyze_primitives(mesh)
        if candidate.primitive_type == request.primitive_type
    )
    fit = PrimitiveFitReport.model_validate(candidate.report())
    if fit.normalized_rms > request.max_normalized_rms:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{request.primitive_type} fit normalized RMS "
                f"{fit.normalized_rms:.6f} exceeds the allowed "
                f"{request.max_normalized_rms:.6f}."
            ),
        )

    export_id = uuid4()
    step_path = EXPORT_DIR / f"{export_id}.step"
    metadata_path = EXPORT_DIR / f"{export_id}.json"
    try:
        export_step(candidate, step_path)
        record = StepExportRecord(
            id=export_id,
            source_mesh_id=mesh_id,
            primitive_type=request.primitive_type,
            unit=source_record.unit,
            fit=fit,
            download_url=f"/api/exports/{export_id}/file",
            generated_at=datetime.now(timezone.utc),
        )
        metadata_path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
    except Exception as exc:
        step_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="STEP export failed.") from exc
    return record


@app.post(
    "/api/meshes/{mesh_id}/step/mesh",
    response_model=StepExportRecord,
    status_code=201,
)
def export_mesh_shape_as_step(mesh_id: UUID) -> StepExportRecord:
    """Export the actual mesh silhouette as a faceted STEP solid."""
    source_record, mesh_path = _load_record(mesh_id)
    if source_record.unit is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Declare working units or apply a physical scale before "
                "exporting mesh STEP."
            ),
        )

    mesh = _load_mesh(mesh_path)
    export_id = uuid4()
    step_path = EXPORT_DIR / f"{export_id}.step"
    metadata_path = EXPORT_DIR / f"{export_id}.json"
    try:
        details = export_mesh_shape_step(mesh, step_path)
        fit = PrimitiveFitReport(
            primitive_type="mesh_solid",
            parameters={
                "extents": [float(value) for value in mesh.extents],
                **details,
            },
            rms_deviation=0.0,
            max_deviation=0.0,
            normalized_rms=0.0,
        )
        record = StepExportRecord(
            id=export_id,
            source_mesh_id=mesh_id,
            primitive_type="mesh_solid",
            unit=source_record.unit,
            fit=fit,
            download_url=f"/api/exports/{export_id}/file",
            generated_at=datetime.now(timezone.utc),
        )
        metadata_path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
    except ValueError as exc:
        step_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        step_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500, detail=f"Mesh STEP export failed: {exc}"
        ) from exc
    return record


@app.get("/api/exports/{export_id}/file")
def download_step_export(export_id: UUID) -> FileResponse:
    step_path = EXPORT_DIR / f"{export_id}.step"
    metadata_path = EXPORT_DIR / f"{export_id}.json"
    if not step_path.exists() or not metadata_path.exists():
        raise HTTPException(status_code=404, detail="STEP export not found.")
    record = StepExportRecord.model_validate_json(
        metadata_path.read_text(encoding="utf-8")
    )
    return FileResponse(
        step_path,
        filename=f"{record.primitive_type}-{record.source_mesh_id}.step",
        media_type="application/step",
    )


@app.get("/api/meshes/{mesh_id}/file")
def download_mesh(mesh_id: UUID) -> FileResponse:
    record, mesh_path = _load_record(mesh_id)
    return FileResponse(
        mesh_path,
        filename=record.provenance.original_filename,
        media_type="application/octet-stream",
    )
