"""
Measured agreement between a recovered CAD solid and its source mesh.

Every reconstruction strategy produces a candidate solid in the same canonical
frame (planar axes on X/Y, the feature axis on +Z with the base at z=0). Scoring
them all with one metric is what lets the pipeline choose a strategy from
evidence instead of from a fixed heuristic.

Volume IoU is the primary metric because it is symmetric, bounded, and
penalises both missing and invented material. It needs an exact boolean kernel;
when none is installed the module degrades to a surface-deviation score, which
ranks candidates consistently even though the numbers are not IoU.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import trimesh

DEVIATION_SAMPLE_LIMIT = 20_000
LOCAL_RESIDUAL_TOLERANCE = 0.005
MAX_RESIDUAL_REGIONS = 12


def boolean_backend_available() -> bool:
    try:
        import manifold3d  # noqa: F401
    except ImportError:
        return False
    return True


def canonical_mesh(
    mesh: trimesh.Trimesh,
    *,
    center: np.ndarray,
    axes: np.ndarray,
    axial_index: int,
    axial_low: float,
) -> trimesh.Trimesh:
    """
    Re-express `mesh` in the frame every candidate solid is built in.

    The two non-axial PCA axes become X and Y, the feature axis becomes +Z, and
    the solid's base sits at z=0. An odd axis permutation mirrors the mesh, so
    the winding is repaired to keep the result a positive-volume solid.
    """
    planar = [index for index in range(3) if index != axial_index]
    local = (np.asarray(mesh.vertices, dtype=np.float64) - center) @ axes
    vertices = np.column_stack(
        (
            local[:, planar[0]],
            local[:, planar[1]],
            local[:, axial_index] - axial_low,
        )
    )
    canonical = trimesh.Trimesh(
        vertices=vertices, faces=np.asarray(mesh.faces).copy(), process=False
    )
    if canonical.is_watertight and canonical.volume < 0:
        canonical.invert()
    return canonical


def as_volume(mesh: trimesh.Trimesh | None) -> trimesh.Trimesh | None:
    """Return a boolean-safe copy of `mesh`, or None if it is not a solid."""
    if mesh is None or len(mesh.faces) == 0:
        return None
    candidate = mesh.copy()
    candidate.remove_unreferenced_vertices()
    # manifold3d already returns a validated watertight volume. Running
    # trimesh.process(validate=True) again can split coincident Boolean seams
    # and turn that valid residual into a non-volume.
    if candidate.is_volume:
        if candidate.volume < 0:
            candidate.invert()
        return candidate
    candidate.process(validate=True)
    candidate.remove_unreferenced_vertices()
    if not candidate.is_watertight:
        candidate.fill_holes()
    if not candidate.is_volume:
        return None
    if candidate.volume < 0:
        candidate.invert()
    return candidate


def volume_iou(
    source: trimesh.Trimesh, candidate: trimesh.Trimesh
) -> float | None:
    """Exact intersection-over-union of two solids, or None if unavailable."""
    if not boolean_backend_available():
        return None
    left = as_volume(source)
    right = as_volume(candidate)
    if left is None or right is None:
        return None
    try:
        intersection = trimesh.boolean.intersection([left, right])
        union = trimesh.boolean.union([left, right])
    except (ValueError, RuntimeError, IndexError):
        return None
    intersection_volume = (
        abs(float(intersection.volume))
        if intersection is not None and len(intersection.faces)
        else 0.0
    )
    union_volume = (
        abs(float(union.volume))
        if union is not None and len(union.faces)
        else 0.0
    )
    if union_volume <= 0.0:
        return None
    return float(np.clip(intersection_volume / union_volume, 0.0, 1.0))


def _sample_points_with_normals(
    mesh: trimesh.Trimesh,
) -> tuple[np.ndarray, np.ndarray]:
    # Face centers have an unambiguous source normal. A vertex on a sharp edge
    # has an averaged normal which can disagree with either adjacent face even
    # when comparing a mesh with an identical copy.
    points = np.asarray(mesh.triangles_center, dtype=np.float64)
    normals = np.asarray(mesh.face_normals, dtype=np.float64)
    if len(points) > DEVIATION_SAMPLE_LIMIT:
        indices = np.linspace(
            0, len(points) - 1, DEVIATION_SAMPLE_LIMIT, dtype=np.int64
        )
        points = points[indices]
        normals = normals[indices]
    return points, normals


def _directed_surface_metrics(
    source: trimesh.Trimesh,
    target: trimesh.Trimesh,
) -> dict[str, float | int | None]:
    empty: dict[str, float | int | None] = {
        "sample_count": 0,
        "mean": None,
        "rms": None,
        "p95": None,
        "max": None,
        "tail_rms": None,
        "normal_alignment": None,
        "normal_error_degrees": None,
    }
    try:
        points, normals = _sample_points_with_normals(source)
        _, distances, triangle_ids = trimesh.proximity.closest_point(
            target, points
        )
    except (ImportError, ValueError, RuntimeError, MemoryError):
        return empty

    valid = (
        np.isfinite(distances)
        & (triangle_ids >= 0)
        & (triangle_ids < len(target.face_normals))
    )
    finite = distances[valid]
    if len(finite) == 0:
        return empty

    source_normals = normals[valid]
    target_normals = np.asarray(target.face_normals, dtype=np.float64)[
        triangle_ids[valid]
    ]
    dots = np.einsum("ij,ij->i", source_normals, target_normals)
    # Absolute alignment is robust to a source mesh whose winding is globally
    # reversed while still penalising geometrically incorrect tangents.
    alignment = np.clip(np.abs(dots), 0.0, 1.0)
    tail_start = float(np.percentile(finite, 90))
    tail = finite[finite >= tail_start]
    return {
        "sample_count": int(len(finite)),
        "mean": float(np.mean(finite)),
        "rms": float(np.sqrt(np.mean(np.square(finite)))),
        "p95": float(np.percentile(finite, 95)),
        "max": float(np.max(finite)),
        "tail_rms": float(np.sqrt(np.mean(np.square(tail)))),
        "normal_alignment": float(np.mean(alignment)),
        "normal_error_degrees": float(
            np.degrees(np.arccos(np.clip(np.mean(alignment), 0.0, 1.0)))
        ),
    }


def symmetric_surface_agreement(
    source: trimesh.Trimesh,
    candidate: trimesh.Trimesh,
) -> dict[str, Any]:
    """
    Measure both missing and invented surfaces, including normal agreement.

    Volume IoU is insensitive to thin local features. The RMS of the worst ten
    percent of surface samples and normal alignment make a missed groove, hole,
    fillet, or sweep visible to hypothesis ranking without replacing IoU.
    """
    forward = _directed_surface_metrics(source, candidate)
    reverse = _directed_surface_metrics(candidate, source)
    numeric_keys = ("rms", "p95", "max", "tail_rms")
    symmetric: dict[str, float | None] = {}
    for key in numeric_keys:
        values = [
            float(report[key])
            for report in (forward, reverse)
            if report.get(key) is not None
        ]
        symmetric[key] = max(values) if values else None

    alignments = [
        float(report["normal_alignment"])
        for report in (forward, reverse)
        if report.get("normal_alignment") is not None
    ]
    normal_alignment = min(alignments) if alignments else None
    scale = max(float(np.linalg.norm(source.extents)), np.finfo(float).eps)
    tail_rms = symmetric["tail_rms"]
    surface_score = (
        float(np.exp(-float(tail_rms) / (scale * 0.01)))
        if tail_rms is not None
        else 0.0
    )
    if normal_alignment is not None:
        surface_score *= 0.7 + 0.3 * normal_alignment
    return {
        "source_to_candidate": forward,
        "candidate_to_source": reverse,
        "symmetric_rms": symmetric["rms"],
        "symmetric_p95": symmetric["p95"],
        "symmetric_max": symmetric["max"],
        "symmetric_tail_rms": tail_rms,
        "normalized_tail_rms": (
            float(tail_rms) / scale if tail_rms is not None else None
        ),
        "normal_alignment": normal_alignment,
        "normal_error_degrees": (
            float(np.degrees(np.arccos(np.clip(normal_alignment, 0.0, 1.0))))
            if normal_alignment is not None
            else None
        ),
        "score": float(np.clip(surface_score, 0.0, 1.0)),
    }


def _face_components(
    mesh: trimesh.Trimesh, selected: np.ndarray
) -> list[np.ndarray]:
    """Connected selected-face components without a networkx dependency."""
    chosen = np.flatnonzero(selected)
    if len(chosen) == 0:
        return []
    parent = np.arange(len(mesh.faces), dtype=np.int64)

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = int(parent[index])
        return index

    for left, right in np.asarray(mesh.face_adjacency, dtype=np.int64):
        if not selected[left] or not selected[right]:
            continue
        left_root, right_root = root(int(left)), root(int(right))
        if left_root != right_root:
            parent[right_root] = left_root

    grouped: dict[int, list[int]] = {}
    for face in chosen:
        grouped.setdefault(root(int(face)), []).append(int(face))
    return [
        np.asarray(faces, dtype=np.int64)
        for faces in sorted(grouped.values(), key=len, reverse=True)
    ]


def _directed_residual_regions(
    source: trimesh.Trimesh,
    target: trimesh.Trimesh,
    *,
    kind: str,
    tolerance: float,
) -> list[dict[str, Any]]:
    centers = np.asarray(source.triangles_center, dtype=np.float64)
    try:
        _, distances, _ = trimesh.proximity.closest_point(target, centers)
    except (ImportError, ValueError, RuntimeError, MemoryError):
        return []
    selected = np.isfinite(distances) & (distances > tolerance)
    total_area = max(float(np.sum(source.area_faces)), np.finfo(float).eps)
    regions: list[dict[str, Any]] = []
    for faces in _face_components(source, selected):
        area = float(np.sum(source.area_faces[faces]))
        if area / total_area < 0.001:
            continue
        points = np.asarray(source.vertices)[np.unique(source.faces[faces])]
        weights = np.asarray(source.area_faces[faces], dtype=np.float64)
        normal = np.average(
            np.asarray(source.face_normals)[faces], axis=0, weights=weights
        )
        norm = float(np.linalg.norm(normal))
        if norm > 0.0:
            normal /= norm
        region_distances = distances[faces]
        regions.append(
            {
                "kind": kind,
                "face_count": int(len(faces)),
                "area": area,
                "area_fraction": area / total_area,
                "centroid": [
                    float(value)
                    for value in np.average(
                        centers[faces], axis=0, weights=weights
                    )
                ],
                "bounds": np.asarray(
                    [points.min(axis=0), points.max(axis=0)]
                ).tolist(),
                "mean_distance": float(np.mean(region_distances)),
                "max_distance": float(np.max(region_distances)),
                "dominant_normal": [float(value) for value in normal],
            }
        )
    return regions


def residual_regions(
    source: trimesh.Trimesh,
    candidate: trimesh.Trimesh,
    *,
    normalized_tolerance: float = LOCAL_RESIDUAL_TOLERANCE,
) -> list[dict[str, Any]]:
    """Connected target-only (missing) and candidate-only (excess) regions."""
    scale = max(float(np.linalg.norm(source.extents)), np.finfo(float).eps)
    tolerance = scale * normalized_tolerance
    regions = _directed_residual_regions(
        source, candidate, kind="missing_material", tolerance=tolerance
    )
    regions.extend(
        _directed_residual_regions(
            candidate, source, kind="excess_material", tolerance=tolerance
        )
    )
    regions.sort(
        key=lambda region: (
            float(region["area_fraction"]) * float(region["mean_distance"])
        ),
        reverse=True,
    )
    return regions[:MAX_RESIDUAL_REGIONS]


def surface_deviation(
    source: trimesh.Trimesh, candidate: trimesh.Trimesh
) -> dict[str, float | int | None]:
    """Distance from source samples to the candidate surface."""
    directed = _directed_surface_metrics(source, candidate)
    return {
        key: directed[key]
        for key in ("sample_count", "mean", "rms", "p95", "max")
    }


@dataclass
class AgreementReport:
    """How well one candidate solid reproduces the source mesh."""

    score: float
    method: str
    volume_iou: float | None = None
    deviation: dict[str, float | int | None] = field(default_factory=dict)
    candidate_volume: float | None = None
    source_volume: float | None = None
    volume_error_percent: float | None = None
    selection_score: float = 0.0
    surface_agreement: dict[str, Any] = field(default_factory=dict)
    residual_regions: list[dict[str, Any]] = field(default_factory=list)
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "method": self.method,
            "volume_iou": self.volume_iou,
            "deviation": dict(self.deviation),
            "candidate_volume": self.candidate_volume,
            "source_volume": self.source_volume,
            "volume_error_percent": self.volume_error_percent,
            "selection_score": self.selection_score,
            "surface_agreement": dict(self.surface_agreement),
            "residual_regions": list(self.residual_regions),
            "detail": self.detail,
        }


def _deviation_score(
    deviation: dict[str, float | int | None], scale: float
) -> float:
    rms = deviation.get("rms")
    if rms is None or scale <= 0.0:
        return 0.0
    # Half a percent of the part's size scores ~0.5; the curve is only used to
    # rank candidates when no boolean kernel is present.
    return float(1.0 / (1.0 + (float(rms) / scale) / 0.005))


def evaluate_candidate(
    source: trimesh.Trimesh,
    candidate: trimesh.Trimesh | None,
    *,
    detail: str | None = None,
    include_residual_regions: bool = False,
) -> AgreementReport:
    """
    Score `candidate` against `source`; both must share the canonical frame.

    A candidate that could not be built scores zero rather than raising, so a
    failed hypothesis simply loses instead of aborting the whole search.
    """
    if candidate is None or len(candidate.faces) == 0:
        return AgreementReport(
            score=0.0, method="unbuildable", detail=detail or "No solid built."
        )

    source_volume = (
        abs(float(source.volume)) if source.is_watertight else None
    )
    candidate_volume = (
        abs(float(candidate.volume)) if candidate.is_watertight else None
    )
    volume_error_percent = (
        abs(candidate_volume - source_volume) / max(source_volume, 1e-12) * 100.0
        if source_volume and candidate_volume is not None
        else None
    )

    iou = volume_iou(source, candidate)
    deviation = surface_deviation(source, candidate)
    surface = symmetric_surface_agreement(source, candidate)
    if iou is not None:
        score, method = iou, "volume_iou"
        normal_alignment = float(surface.get("normal_alignment") or 0.0)
        selection_score = (
            0.7 * iou
            + 0.2 * float(surface["score"])
            + 0.1 * normal_alignment
        )
    else:
        scale = float(np.linalg.norm(source.extents))
        score, method = _deviation_score(deviation, scale), "surface_deviation"
        selection_score = float(surface["score"])

    return AgreementReport(
        score=float(score),
        method=method,
        volume_iou=iou,
        deviation=deviation,
        candidate_volume=candidate_volume,
        source_volume=source_volume,
        volume_error_percent=volume_error_percent,
        selection_score=float(np.clip(selection_score, 0.0, 1.0)),
        surface_agreement=surface,
        residual_regions=(
            residual_regions(source, candidate)
            if include_residual_regions
            else []
        ),
        detail=detail,
    )


def stacked_extrusion_solid(
    components: list[tuple[Any, float, float]],
) -> trimesh.Trimesh | None:
    """Union of (polygon, depth, start_offset) prisms in the canonical frame."""
    solids: list[trimesh.Trimesh] = []
    for polygon, depth, start_offset in components:
        if depth <= 0.0 or polygon.is_empty or polygon.area <= 0.0:
            continue
        try:
            solid = trimesh.creation.extrude_polygon(
                polygon, height=float(depth), engine="earcut"
            )
        except (ImportError, ValueError, RuntimeError, IndexError):
            return None
        solid.apply_translation([0.0, 0.0, float(start_offset)])
        solids.append(solid)
    if not solids:
        return None
    if len(solids) == 1:
        return as_volume(solids[0]) or solids[0]
    if boolean_backend_available():
        volumes = [solid for solid in map(as_volume, solids) if solid is not None]
        if len(volumes) == len(solids):
            try:
                return trimesh.boolean.union(volumes)
            except (ValueError, RuntimeError, IndexError):
                pass
    # Stacked prisms only touch at their end caps, so concatenation is a fair
    # fallback for deviation scoring even though it is not a clean solid.
    return trimesh.util.concatenate(solids)
