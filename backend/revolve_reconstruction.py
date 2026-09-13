"""
Recover a single revolve feature from a mesh that is a body of revolution.

Turned and moulded parts - sleeves, bottles, bosses, spacers - are one sketch
revolved about an axis. The prismatic recovery path cannot express that: it can
only stack constant cross-sections along an axis, so a tapered or stepped
revolve degrades into a slab whose profile is wrong everywhere except the one
slice it was sampled from.

The profile here is built from the actual radial extent of the mesh at many
heights, including any concentric bore, so steps and chamfers survive.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import trimesh
from shapely.geometry import Polygon

from parametric_reconstruction import (
    UNIT_TO_METERS,
    LengthUnit,
    ParametricReconstructionError,
    _coordinates,
    _right_handed_pca,
)
from solid_agreement import as_volume, canonical_mesh, evaluate_candidate

AXIS_TOLERANCE_RATIO = 1e-3
DEFAULT_SLICE_COUNT = 96
DEFAULT_REVOLVE_SECTIONS = 128
OUTER_RADIUS_PERCENTILE = 90.0


def _basis_for_world_axis(axis_world: np.ndarray) -> np.ndarray:
    """Right-handed planar basis whose third column is the requested axis."""
    axis = np.asarray(axis_world, dtype=np.float64)
    magnitude = float(np.linalg.norm(axis))
    if magnitude <= np.finfo(float).eps:
        raise ParametricReconstructionError(
            "A surface-derived revolve axis has zero length."
        )
    axis /= magnitude
    reference = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(reference, axis))) > 0.9:
        reference = np.array([0.0, 1.0, 0.0])
    first = np.cross(reference, axis)
    first /= max(float(np.linalg.norm(first)), np.finfo(float).eps)
    second = np.cross(axis, first)
    basis = np.column_stack((first, second, axis))
    if np.linalg.det(basis) < 0.0:
        basis[:, 0] *= -1.0
    return basis


def _section_rings(
    canonical: trimesh.Trimesh, height: float
) -> tuple[Polygon, list[Polygon]] | None:
    """Cross-section at `height`, projected straight onto canonical XY."""
    section = canonical.section(
        plane_origin=[0.0, 0.0, float(height)], plane_normal=[0.0, 0.0, 1.0]
    )
    if section is None:
        return None
    rings: list[Polygon] = []
    for discrete in section.discrete:
        points = np.asarray(discrete, dtype=np.float64)[:, :2]
        if len(points) < 4:
            continue
        ring = Polygon(points)
        if not ring.is_valid:
            ring = ring.buffer(0)
        if isinstance(ring, Polygon) and not ring.is_empty and ring.area > 1e-12:
            rings.append(ring)
    if not rings:
        return None
    outer = max(rings, key=lambda candidate: candidate.area)
    holes = [
        ring
        for ring in rings
        if ring is not outer and outer.contains(ring.representative_point())
    ]
    return outer, holes


def _axis_origin(canonical: trimesh.Trimesh, samples: int = 24) -> np.ndarray:
    """
    Locate the revolve axis in XY.

    The PCA centroid is pulled off-axis by asymmetric features such as a lip or
    a flange, so the median of the cross-section centroids is used instead: it
    ignores a minority of skewed slices.
    """
    low, high = float(canonical.bounds[0][2]), float(canonical.bounds[1][2])
    span = high - low
    centroids: list[np.ndarray] = []
    for fraction in np.linspace(0.08, 0.92, samples):
        rings = _section_rings(canonical, low + span * float(fraction))
        if rings is None:
            continue
        centroids.append(np.asarray(rings[0].centroid.coords[0], dtype=np.float64))
    if not centroids:
        return np.zeros(2, dtype=np.float64)
    return np.median(np.vstack(centroids), axis=0)


def _ring_radii(ring: Polygon) -> np.ndarray:
    coords = np.asarray(ring.exterior.coords, dtype=np.float64)
    return np.linalg.norm(coords, axis=1)


def _repair_occluded_bore(
    inner: np.ndarray, outer: np.ndarray
) -> tuple[np.ndarray, int]:
    """
    Bridge short missing-hole runs caused by radial openings into an axial bore.

    A radial hole merges the inner and outer section contours, so no closed
    inner ring exists at those heights. If comparable bore radii resume on both
    sides of a bounded gap, continuity is stronger evidence than treating the
    intervening slices as solid. Unbounded gaps remain untouched so blind bores
    still terminate correctly.
    """
    repaired = np.asarray(inner, dtype=np.float64).copy()
    missing = repaired <= 0.0
    maximum_gap = max(2, int(np.ceil(len(repaired) * 0.2)))
    repaired_count = 0
    start: int | None = None
    for index in range(len(repaired) + 1):
        is_missing = index < len(repaired) and bool(missing[index])
        if is_missing and start is None:
            start = index
            continue
        if is_missing or start is None:
            continue
        end = index - 1
        gap_length = end - start + 1
        left_index, right_index = start - 1, index
        if (
            left_index >= 0
            and right_index < len(repaired)
            and gap_length <= maximum_gap
        ):
            left, right = repaired[left_index], repaired[right_index]
            reference = max(
                float(outer[left_index]),
                float(outer[right_index]),
                np.finfo(float).eps,
            )
            if abs(float(left - right)) / reference <= 0.2:
                repaired[start:index] = np.linspace(
                    left, right, gap_length + 2
                )[1:-1]
                repaired_count += gap_length
        start = None
    return repaired, repaired_count


def _radial_profile(
    canonical: trimesh.Trimesh,
    slice_count: int,
    outer_radius_percentile: float,
) -> dict[str, Any]:
    """Outer radius, bore radius and roundness at evenly spaced heights."""
    low, high = float(canonical.bounds[0][2]), float(canonical.bounds[1][2])
    span = high - low
    if span <= 0.0:
        raise ParametricReconstructionError(
            "The mesh has no extent along the candidate revolve axis."
        )

    edges = np.linspace(low, high, slice_count + 1)
    midpoints = (edges[:-1] + edges[1:]) * 0.5
    heights: list[float] = []
    outer_radii: list[float] = []
    observed_outer_radii: list[float] = []
    inner_radii: list[float] = []
    roundness: list[float] = []

    for height in midpoints:
        rings = _section_rings(canonical, float(height))
        if rings is None:
            continue
        outer_ring, holes = rings
        radii = _ring_radii(outer_ring)
        observed_outer = float(np.max(radii))
        # A local tab or nozzle seam must not be revolved around the complete
        # part. Recover the dominant turned wall and leave sparse asymmetric
        # protrusions for the residual feature loop.
        outer = float(np.percentile(radii, outer_radius_percentile))
        if outer <= 0.0:
            continue
        heights.append(float(height))
        outer_radii.append(outer)
        observed_outer_radii.append(observed_outer)
        roundness.append(float(np.std(radii) / max(outer, 1e-12)))

        bore = 0.0
        for hole in holes:
            centroid = np.asarray(hole.centroid.coords[0], dtype=np.float64)
            # Only a hole sitting on the axis is a bore; an off-axis pocket is
            # a separate feature and must not be revolved away.
            if float(np.linalg.norm(centroid)) > outer * 0.2:
                continue
            bore = max(bore, float(np.median(_ring_radii(hole))))
        inner_radii.append(bore)

    if len(heights) < 6:
        raise ParametricReconstructionError(
            "Could not recover enough cross-sections along the revolve axis."
        )

    inner_array, repaired_bore_slices = _repair_occluded_bore(
        np.asarray(inner_radii, dtype=np.float64),
        np.asarray(outer_radii, dtype=np.float64),
    )
    return {
        "heights": np.asarray(heights, dtype=np.float64),
        "outer": np.asarray(outer_radii, dtype=np.float64),
        "observed_outer": np.asarray(
            observed_outer_radii, dtype=np.float64
        ),
        "inner": inner_array,
        "bore_interpolated_slice_count": repaired_bore_slices,
        "roundness": float(np.mean(roundness)),
        "roundness_p95": float(np.percentile(roundness, 95)),
        "axial_low": low,
        "axial_high": high,
    }


def _centred_canonical(
    mesh: trimesh.Trimesh,
    *,
    center: np.ndarray,
    axes: np.ndarray,
    axis_index: int,
    axial_low: float,
) -> tuple[trimesh.Trimesh, np.ndarray]:
    """Canonical mesh with the revolve axis moved onto X=Y=0."""
    canonical = canonical_mesh(
        mesh,
        center=center,
        axes=axes,
        axial_index=axis_index,
        axial_low=axial_low,
    )
    origin = _axis_origin(canonical)
    canonical.apply_translation([-float(origin[0]), -float(origin[1]), 0.0])
    return canonical, origin


def _best_revolve_axis(
    mesh: trimesh.Trimesh, center: np.ndarray, axes: np.ndarray, local: np.ndarray
) -> int:
    """
    Pick the axis whose cross-sections are most circular.

    Extent is a misleading signal here: a bottle's revolve axis is its longest
    axis but a washer's is its shortest, so roundness is measured directly.
    """
    best_index, best_roundness = 0, float("inf")
    for index in range(3):
        try:
            canonical, _ = _centred_canonical(
                mesh,
                center=center,
                axes=axes,
                axis_index=index,
                axial_low=float(local[:, index].min()),
            )
            roundness = _radial_profile(
                canonical, 24, OUTER_RADIUS_PERCENTILE
            )["roundness"]
        except (ParametricReconstructionError, ValueError, RuntimeError):
            continue
        if roundness < best_roundness:
            best_index, best_roundness = index, roundness
    return best_index


def _profile_polygon(profile: dict[str, Any], simplify_tolerance: float) -> Polygon:
    """
    Material region in the (radius, height) half-plane.

    Each slice contributes the band it actually occupies, so a bore, a step or
    a counterbore all fall out of the union without any special casing.
    """
    heights = profile["heights"]
    outer = profile["outer"]
    # A bore can never reach the outer wall; clamping keeps the ring simple so
    # the inner and outer walls cannot cross and self-intersect the profile.
    inner = np.minimum(profile["inner"], outer * 0.999)
    low, high = profile["axial_low"], profile["axial_high"]

    outer_wall = [(float(outer[0]), float(low))]
    outer_wall += [
        (float(radius), float(height)) for height, radius in zip(heights, outer)
    ]
    outer_wall.append((float(outer[-1]), float(high)))

    inner_wall = [(float(inner[-1]), float(high))]
    inner_wall += [
        (float(radius), float(height))
        for height, radius in zip(heights[::-1], inner[::-1])
    ]
    inner_wall.append((float(inner[0]), float(low)))

    merged = Polygon(outer_wall + inner_wall)
    if not merged.is_valid:
        merged = merged.buffer(0)
    if merged.geom_type == "MultiPolygon":
        merged = max(merged.geoms, key=lambda item: item.area)
    if not isinstance(merged, Polygon) or merged.is_empty or merged.area <= 0.0:
        raise ParametricReconstructionError(
            "Could not close the revolve profile into a single region."
        )

    simplified = merged.simplify(simplify_tolerance, preserve_topology=True)
    if (
        not isinstance(simplified, Polygon)
        or simplified.is_empty
        or not simplified.is_valid
        or simplified.area <= 0.0
    ):
        return merged
    return simplified


def _open_axis_profile(
    polygon: Polygon, tolerance: float
) -> np.ndarray | None:
    """
    Rewrite an axis-touching ring as a polyline running axis -> wall -> axis.

    Revolving the ring as-is would sweep its zero-radius edge into degenerate
    geometry, so that edge is dropped and only its endpoints are kept.
    """
    coords = np.asarray(polygon.exterior.coords, dtype=np.float64)[:-1]
    if len(coords) < 3:
        return None
    on_axis = coords[:, 0] <= tolerance
    if not on_axis.any():
        return None

    count = len(coords)
    doubled = np.concatenate((on_axis, on_axis))
    best_start, best_length = 0, 0
    index = 0
    while index < len(doubled):
        if not doubled[index]:
            index += 1
            continue
        end = index
        while end < len(doubled) and doubled[end] and end - index < count:
            end += 1
        if end - index > best_length:
            best_start, best_length = index, end - index
        index = end
    if best_length == 0 or best_length >= count - 1:
        return None

    last_axis = (best_start + best_length - 1) % count
    first_axis = best_start % count
    walk = [coords[last_axis]]
    cursor = (last_axis + 1) % count
    while cursor != first_axis:
        walk.append(coords[cursor])
        cursor = (cursor + 1) % count
    walk.append(coords[first_axis])
    return np.asarray(walk, dtype=np.float64)


def revolve_profile_solid(
    polygon: Polygon,
    *,
    tolerance: float,
    sections: int = DEFAULT_REVOLVE_SECTIONS,
) -> trimesh.Trimesh | None:
    """Sweep a (radius, height) region 360 degrees about the Z axis."""
    try:
        if float(np.min(np.asarray(polygon.exterior.coords)[:, 0])) > tolerance:
            coords = np.asarray(polygon.exterior.coords, dtype=np.float64)
            solid = trimesh.creation.revolve(coords, sections=sections)
        else:
            walk = _open_axis_profile(polygon, tolerance)
            if walk is None:
                return None
            solid = trimesh.creation.revolve(walk, sections=sections)
    except (ValueError, RuntimeError, IndexError):
        return None
    solid.process(validate=True)
    if solid.is_watertight and solid.volume < 0:
        solid.invert()
    return solid


def fit_axisymmetric_residual(
    component: trimesh.Trimesh,
    *,
    axis_index: int = 2,
    slice_count: int = 48,
    simplify_ratio: float = 0.004,
    maximum_roundness: float = 0.05,
    maximum_roundness_p95: float = 0.08,
) -> tuple[trimesh.Trimesh, Polygon, dict[str, Any]] | None:
    """
    Fit a full-turn cutter to an annular residual around canonical Z.

    This intentionally requires the residual's axis to already coincide with
    the recipe axis. Off-axis revolved cuts require an additional sketch-frame
    representation and are left to linear residual proposals for now.
    """
    if axis_index not in (0, 1, 2):
        return None
    source = component.copy()
    if axis_index != 2:
        planar = [index for index in range(3) if index != axis_index]
        canonical = np.asarray(source.vertices, dtype=np.float64)
        local = np.empty_like(canonical)
        local[:, 0] = canonical[:, planar[0]]
        local[:, 1] = canonical[:, planar[1]]
        local[:, 2] = canonical[:, axis_index]
        source = trimesh.Trimesh(
            vertices=local,
            faces=np.asarray(source.faces).copy(),
            process=False,
        )
        source.process(validate=True)
        if source.is_watertight and source.volume < 0:
            source.invert()
    volume = as_volume(source)
    if volume is None:
        return None
    scale = max(float(np.linalg.norm(volume.extents)), np.finfo(float).eps)
    origin = _axis_origin(volume)
    if float(np.linalg.norm(origin)) > scale * 0.02:
        return None
    try:
        profile = _radial_profile(volume, slice_count, 100.0)
    except (ParametricReconstructionError, ValueError, RuntimeError, IndexError):
        return None
    if (
        float(profile["roundness"]) > maximum_roundness
        or float(profile["roundness_p95"]) > maximum_roundness_p95
    ):
        return None
    reference_radius = float(np.max(profile["outer"]))
    tolerance = max(reference_radius * AXIS_TOLERANCE_RATIO, 1e-9)
    # An annular inner wall distinguishes a revolved groove from a centered
    # cylindrical pocket, which is cleaner as a native Cut-Extrude.
    if float(np.max(profile["inner"])) <= tolerance:
        return None
    try:
        polygon = _profile_polygon(
            profile, max(reference_radius * simplify_ratio, 1e-7)
        )
    except (ParametricReconstructionError, ValueError, RuntimeError):
        return None
    solid = as_volume(
        revolve_profile_solid(polygon, tolerance=tolerance)
    )
    if solid is None:
        return None
    profile["axis_origin"] = origin
    profile["axis_index"] = axis_index
    return solid, polygon, profile


def build_revolve_recipe(
    mesh: trimesh.Trimesh,
    unit: LengthUnit,
    *,
    axis_index: int | None = None,
    slice_count: int = DEFAULT_SLICE_COUNT,
    simplify_ratio: float = 0.004,
    include_residual_regions: bool = False,
    outer_radius_percentile: float = OUTER_RADIUS_PERCENTILE,
    axis_world: list[float] | np.ndarray | None = None,
) -> dict[str, object]:
    """Recover an editable single-revolve feature recipe from `mesh`."""
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ParametricReconstructionError(
            "Revolve reconstruction requires a triangle mesh."
        )
    if unit not in UNIT_TO_METERS:
        raise ParametricReconstructionError(f"Unsupported recipe unit: {unit}")

    if axis_world is not None and axis_index is not None:
        raise ParametricReconstructionError(
            "Specify either a PCA axis index or a world-space revolve axis, not both."
        )

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    axis_source = "pca"
    if axis_world is not None:
        center = vertices.mean(axis=0)
        axes = _basis_for_world_axis(np.asarray(axis_world, dtype=np.float64))
        axis_index = 2
        axis_source = "surface_patch"
    else:
        center, axes = _right_handed_pca(vertices)
    local = (vertices - center) @ axes
    spans = np.ptp(local, axis=0)
    if axis_index is None:
        axis_index = _best_revolve_axis(mesh, center, axes, local)
    if axis_index not in (0, 1, 2):
        raise ParametricReconstructionError(
            f"Revolve axis index must be 0, 1 or 2 (got {axis_index})."
        )
    if not 50.0 <= outer_radius_percentile <= 100.0:
        raise ParametricReconstructionError(
            "Outer-radius percentile must be between 50 and 100."
        )

    axial_low = float(local[:, axis_index].min())
    axial_high = float(local[:, axis_index].max())
    canonical, origin = _centred_canonical(
        mesh,
        center=center,
        axes=axes,
        axis_index=axis_index,
        axial_low=axial_low,
    )

    profile = _radial_profile(
        canonical, slice_count, outer_radius_percentile
    )
    reference_radius = float(np.max(profile["outer"]))
    observed_radius = float(np.max(profile["observed_outer"]))
    tolerance = max(reference_radius * AXIS_TOLERANCE_RATIO, 1e-9)
    polygon = _profile_polygon(
        profile, max(reference_radius * simplify_ratio, 1e-7)
    )
    solid = revolve_profile_solid(polygon, tolerance=tolerance)
    agreement = evaluate_candidate(
        canonical,
        solid,
        detail=(
            f"revolve about {axis_source} axis "
            f"{[float(value) for value in axes[:, axis_index]]}"
        ),
        include_residual_regions=include_residual_regions,
    )

    bore_radius = float(np.max(profile["inner"]))
    height = float(profile["axial_high"] - profile["axial_low"])
    roundness = float(profile["roundness"])
    confidence = float(np.clip(agreement.score, 0.0, 1.0))

    sketch = {
        "name": "CADView Revolve Profile",
        "plane": "Front Plane",
        "outer_loop": {
            "kind": "polyline",
            "points": _coordinates(polygon.exterior.coords),
        },
        "inner_loops": [],
        "centerline": [[0.0, 0.0], [0.0, height]],
    }
    features = [
        {
            "id": "base-revolve-1",
            "name": "CADView Core Revolve",
            "type": "revolve",
            "angle_degrees": 360.0,
            "axis": {"kind": "sketch_centerline", "points": [[0.0, 0.0], [0.0, height]]},
            "role": "base",
            "sketch": sketch,
        }
    ]

    warnings: list[str] = []
    if roundness > 0.05:
        warnings.append(
            f"Cross-sections deviate from circular by {roundness * 100:.1f}% on "
            "average, so this part is only approximately a body of revolution."
        )
    if agreement.volume_iou is not None and agreement.volume_iou < 0.9:
        warnings.append(
            f"The revolve reproduces {agreement.volume_iou * 100:.1f}% of the "
            "mesh volume; non-axisymmetric detail is not captured by this "
            "single feature."
        )
    if bore_radius > 0.0:
        warnings.append(
            f"A concentric bore of radius {bore_radius:.3f} {unit} was folded "
            "into the revolve profile."
        )

    return {
        "schema_version": "3.0",
        "strategy": "revolve_reconstruction",
        "unit": unit,
        "confidence": confidence,
        "source": {
            "face_count": int(len(mesh.faces)),
            "watertight": bool(mesh.is_watertight),
            "extents": [float(value) for value in mesh.extents],
        },
        "features": features,
        "diagnostics": {
            "pca_spans": [float(value) for value in spans],
            "revolve_axis_index": axis_index,
            "revolve_axis_source": axis_source,
            "revolve_axis_world": [float(value) for value in axes[:, axis_index]],
            "axis_origin_offset": [float(origin[0]), float(origin[1])],
            "profile_height": height,
            "profile_point_count": len(sketch["outer_loop"]["points"]),
            "maximum_radius": reference_radius,
            "observed_maximum_radius": observed_radius,
            "outer_radius_percentile": outer_radius_percentile,
            "bore_radius": bore_radius,
            "bore_interpolated_slice_count": int(
                profile["bore_interpolated_slice_count"]
            ),
            "roundness_error": roundness,
            "roundness_error_p95": float(profile["roundness_p95"]),
            "slice_count": int(len(profile["heights"])),
            "agreement": agreement.as_dict(),
            "deviation": dict(agreement.deviation),
            "reconstructed_volume": agreement.candidate_volume,
            "source_volume": agreement.source_volume,
            "volume_error_percent": agreement.volume_error_percent,
            "canonical_frame": {
                "center_world": [float(value) for value in center],
                "plane_basis_world": np.asarray(
                    axes[:, [i for i in range(3) if i != axis_index]]
                ).tolist(),
                "axial_low": axial_low,
                "axial_high": axial_high,
            },
        },
        "warnings": warnings,
    }
