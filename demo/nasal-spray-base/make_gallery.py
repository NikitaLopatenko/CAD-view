"""Generate nasal-spray demo gallery images and a short MP4 for the README."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import imageio_ffmpeg
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from matplotlib import patheffects
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
GALLERY = ROOT / "gallery"
FRAMES = GALLERY / "frames"
VIDEO = ROOT / "cadview-nasal-spray-demo.mp4"

MESH_PATH = ROOT / "reconstruction-60k.stl"
CAD_PATH = ROOT / "recovered-revolve.stl"
PHOTO_CANDIDATES = [
    ROOT / "gallery-bottle-photo.jpg",
    ROOT / "input-photo.png",
]


def _font(size: int) -> ImageFont.ImageFont:
    for name in (
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
    ):
        path = Path(name)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(path, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError(f"Expected triangle mesh at {path}")
    mesh.remove_unreferenced_vertices()
    return mesh


def half_cut(mesh: trimesh.Trimesh, axis: int = 0) -> trimesh.Trimesh:
    """Keep faces whose centroids lie on the positive half-space."""
    centers = mesh.triangles_center
    keep = centers[:, axis] >= 0.0
    if int(keep.sum()) < 100:
        keep = centers[:, axis] <= 0.0
    return mesh.submesh([keep], append=True)


def render_mesh(
    mesh: trimesh.Trimesh,
    out: Path,
    *,
    elev: float,
    azim: float,
    color: str,
    title: str,
    alpha: float = 1.0,
    edge: bool = False,
) -> None:
    fig = plt.figure(figsize=(8, 8), dpi=140)
    ax = fig.add_subplot(111, projection="3d")
    faces = mesh.triangles
    collection = Poly3DCollection(
        faces,
        facecolors=color,
        edgecolors="#1f2937" if edge else color,
        linewidths=0.05 if edge else 0.0,
        alpha=alpha,
    )
    ax.add_collection3d(collection)
    bounds = mesh.bounds
    center = bounds.mean(axis=0)
    span = float(np.max(bounds[1] - bounds[0]) * 0.62)
    ax.set_xlim(center[0] - span, center[0] + span)
    ax.set_ylim(center[1] - span, center[1] + span)
    ax.set_zlim(center[2] - span, center[2] + span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#0f172a")
    ax.text2D(
        0.03,
        0.96,
        title,
        transform=ax.transAxes,
        color="#e2e8f0",
        fontsize=13,
        fontweight="bold",
        path_effects=[patheffects.withStroke(linewidth=3, foreground="#0f172a")],
    )
    fig.tight_layout(pad=0.2)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def render_overlay(
    mesh: trimesh.Trimesh,
    cad: trimesh.Trimesh,
    out: Path,
    *,
    elev: float,
    azim: float,
    title: str,
) -> None:
    fig = plt.figure(figsize=(8, 8), dpi=140)
    ax = fig.add_subplot(111, projection="3d")
    mesh_col = Poly3DCollection(
        mesh.triangles,
        facecolors="#64748b",
        edgecolors="#64748b",
        alpha=0.28,
        linewidths=0.0,
    )
    cad_col = Poly3DCollection(
        cad.triangles,
        facecolors="#38bdf8",
        edgecolors="#0ea5e9",
        alpha=0.72,
        linewidths=0.02,
    )
    ax.add_collection3d(mesh_col)
    ax.add_collection3d(cad_col)
    bounds = np.vstack([mesh.bounds, cad.bounds])
    lo, hi = bounds.min(axis=0), bounds.max(axis=0)
    center = (lo + hi) / 2.0
    span = float(np.max(hi - lo) * 0.62)
    ax.set_xlim(center[0] - span, center[0] + span)
    ax.set_ylim(center[1] - span, center[1] + span)
    ax.set_zlim(center[2] - span, center[2] + span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#0f172a")
    ax.text2D(
        0.03,
        0.96,
        title,
        transform=ax.transAxes,
        color="#e2e8f0",
        fontsize=13,
        fontweight="bold",
        path_effects=[patheffects.withStroke(linewidth=3, foreground="#0f172a")],
    )
    fig.tight_layout(pad=0.2)
    fig.savefig(out, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def render_profile_cut(mesh: trimesh.Trimesh, out: Path, title: str) -> None:
    """2D radial profile from a longitudinal cut (x≈0 slice)."""
    verts = mesh.vertices
    # Keep vertices near the x=0 cutting plane and project to (radius, z).
    near = np.abs(verts[:, 0]) < (0.035 * float(np.ptp(verts[:, 1]) + 1e-6) + 0.25)
    pts = verts[near]
    if len(pts) < 50:
        pts = verts
    radius = np.sqrt(pts[:, 0] ** 2 + pts[:, 1] ** 2)
    z = pts[:, 2]

    fig, ax = plt.subplots(figsize=(8, 8), dpi=140)
    ax.scatter(radius, z, s=2.5, c="#38bdf8", alpha=0.55, linewidths=0)
    ax.scatter(-radius, z, s=2.5, c="#38bdf8", alpha=0.55, linewidths=0)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("radial extent (mm)", color="#cbd5e1")
    ax.set_ylabel("height (mm)", color="#cbd5e1")
    ax.set_title(title, color="#e2e8f0", fontsize=13, fontweight="bold", loc="left")
    ax.tick_params(colors="#94a3b8")
    for spine in ax.spines.values():
        spine.set_color("#334155")
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#0f172a")
    fig.tight_layout(pad=0.4)
    fig.savefig(out, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)


def title_card(out: Path, lines: list[str], subtitle: str | None = None) -> None:
    img = Image.new("RGB", (1280, 720), "#0f172a")
    draw = ImageDraw.Draw(img)
    # Accent bar
    draw.rectangle((0, 0, 18, 720), fill="#38bdf8")
    y = 180
    draw.text((72, y), lines[0], font=_font(54), fill="#f8fafc")
    y += 80
    for line in lines[1:]:
        draw.text((72, y), line, font=_font(36), fill="#e2e8f0")
        y += 56
    if subtitle:
        draw.text((72, 620), subtitle, font=_font(24), fill="#94a3b8")
    img.save(out, quality=95)


def fit_frame(path: Path, size: tuple[int, int] = (1280, 720)) -> Image.Image:
    src = Image.open(path).convert("RGB")
    canvas = Image.new("RGB", size, "#0f172a")
    src.thumbnail(size, Image.Resampling.LANCZOS)
    x = (size[0] - src.width) // 2
    y = (size[1] - src.height) // 2
    canvas.paste(src, (x, y))
    return canvas


def caption(img: Image.Image, text: str) -> Image.Image:
    draw = ImageDraw.Draw(img)
    bar_h = 64
    draw.rectangle((0, img.height - bar_h, img.width, img.height), fill="#020617")
    draw.text((28, img.height - 46), text, font=_font(26), fill="#e2e8f0")
    return img


def build_video(frame_paths: list[Path], out: Path, seconds_each: float = 2.4) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    list_file = GALLERY / "ffmpeg-frames.txt"
    lines = []
    for path in frame_paths:
        # ffmpeg concat demuxer needs forward slashes / escaped quotes
        p = path.resolve().as_posix().replace("'", r"'\''")
        lines.append(f"file '{p}'")
        lines.append(f"duration {seconds_each}")
    # Repeat last frame so duration applies
    last = frame_paths[-1].resolve().as_posix().replace("'", r"'\''")
    lines.append(f"file '{last}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-vf",
        "fps=30,format=yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    GALLERY.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)

    mesh = load_mesh(MESH_PATH)
    cad = load_mesh(CAD_PATH)
    cut = half_cut(mesh, axis=0)

    # 1) Physical photo
    photo_src = next((p for p in PHOTO_CANDIDATES if p.exists()), None)
    if photo_src is not None:
        photo_out = GALLERY / "01-physical-bottle.jpg"
        Image.open(photo_src).convert("RGB").save(photo_out, quality=92)

    # 2-4) Mesh views
    render_mesh(
        mesh,
        GALLERY / "02-observed-mesh.png",
        elev=18,
        azim=35,
        color="#94a3b8",
        title="Observed mesh (60k faces)",
    )
    render_mesh(
        mesh,
        GALLERY / "03-mesh-three-quarter.png",
        elev=28,
        azim=125,
        color="#cbd5e1",
        title="Observed mesh · alternate view",
        edge=True,
    )
    render_mesh(
        cut,
        GALLERY / "04-mesh-cutaway.png",
        elev=12,
        azim=0,
        color="#fbbf24",
        title="Cutaway view of observed mesh",
        edge=True,
    )

    # 5) Profile cut
    render_profile_cut(
        mesh,
        GALLERY / "05-radial-profile-cut.png",
        title="Longitudinal / radial profile from mesh cut",
    )

    # 6-7) CAD solid + overlay
    render_mesh(
        cad,
        GALLERY / "06-recovered-revolve.png",
        elev=18,
        azim=40,
        color="#38bdf8",
        title="Recovered native revolve solid",
    )
    render_overlay(
        mesh,
        cad,
        GALLERY / "07-mesh-vs-cad-overlay.png",
        elev=20,
        azim=48,
        title="Mesh (gray) vs recovered CAD (cyan)",
    )

    # Title / metrics cards
    title_card(
        GALLERY / "00-title.png",
        ["CAD-View", "Photo / mesh → editable SolidWorks"],
        subtitle="Nasal-spray demo · reverse engineering with provenance",
    )
    title_card(
        GALLERY / "08-metrics.png",
        [
            "Native revolve selected",
            "Volume error ≈ 1.8%",
            "IoU ≈ 0.906  ·  13-pt profile sketch",
        ],
        subtitle="Old default extrude: ~47.6% volume error",
    )
    title_card(
        GALLERY / "09-end.png",
        ["Editable history,", "not a dumb solid."],
        subtitle="github.com/NikitaLopatenko/CAD-view",
    )

    # Video frames (1280x720)
    sequence = [
        (GALLERY / "00-title.png", "CAD-View"),
        (GALLERY / "01-physical-bottle.jpg", "Physical part"),
        (GALLERY / "02-observed-mesh.png", "Observed reconstruction mesh"),
        (GALLERY / "04-mesh-cutaway.png", "Cutaway of observed mesh"),
        (GALLERY / "05-radial-profile-cut.png", "Radial profile from cut"),
        (GALLERY / "06-recovered-revolve.png", "Recovered revolve solid"),
        (GALLERY / "07-mesh-vs-cad-overlay.png", "Mesh vs CAD agreement"),
        (GALLERY / "08-metrics.png", "Agreement metrics"),
        (GALLERY / "09-end.png", "Open source on GitHub"),
    ]

    frame_paths: list[Path] = []
    for idx, (src, label) in enumerate(sequence):
        if not src.exists():
            continue
        frame = caption(fit_frame(src), label)
        dest = FRAMES / f"frame-{idx:02d}.png"
        frame.save(dest)
        frame_paths.append(dest)

    if len(frame_paths) >= 2:
        build_video(frame_paths, VIDEO, seconds_each=2.5)
        print(f"Wrote video: {VIDEO}")
    print(f"Wrote gallery: {GALLERY}")


if __name__ == "__main__":
    main()
