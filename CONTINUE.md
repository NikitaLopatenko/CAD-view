# CAD-View resume point (2026-07-27 evening)

Say: **continue from CONTINUE.md**

---

## Status (end of this session)

Two working product paths:

1. **Mesh → editable SolidWorks** (cam / prismatic parts)
2. **Photos → observed mesh** (Meshroom + VGGT; TSDF surface fusion)

Do not shut down with unfinished Meshroom/VGGT jobs; validation runs already finished and wrote under `backend/reconstructions/` (gitignored).

---

## Image → mesh (latest)

### Architecture now
- **Meshroom:** full-frame FeatureExtraction / SfM → object masks only on `PrepareDenseScene` → densify → meshing helpers
- **VGGT:** full-frame photos into the network → SAM masks applied only during **confidence-masked TSDF fusion**
- Abandoned: raw occupancy voxels + Marching Cubes on unoriented VGGT points (caused 1200+ component blobs)
- Abandoned: blacking out VGGT inputs with masks (destroyed pose context)

### Real bottle validation (`9ed3a5a8-…`)
- Old blob path: ~1205 components, not watertight
- Full-scene VGGT + masked TSDF: **1 component**, watertight, ~22k faces
- Body recognizable; glossy white nozzle still weaker (depth evidence sparse there)

### Watertight / scan-cleanup work (`a5ea4ef7-…`)
- Published observed mesh: 48,928 faces, 1 component, **not watertight**
- Exact topology diagnosis: only 26 boundary edges in one crop-boundary loop
- Euler −115 shows many false tunnels/handles despite the single opening
- Added a 2-voxel positive TSDF guard so Marching Cubes cannot exit the crop volume
- Added arbitrary simple-loop triangulation (Earcut on least-squares plane), not only triangle/quad filling
- Added a separate **Watertight scan proxy** mode:
  - voxel wrap at adjustable resolution
  - adjustable narrow-defect closing
  - non-shrinking Taubin smoothing
  - symmetric RMS/p95/max deviation report
  - observed source remains immutable and inference requires review
- Current derived proxy ID: `3e23a890-b796-4318-8055-141377f14ce9`
  - watertight, 106,008 faces
  - 1 boundary loop filled
  - normalized symmetric RMS ≈ 0.567%
  - still not automatically “CAD-ready”: Euler −28 means false handles remain
- Research/architecture canvas:
  `scan-to-watertight-strategy.canvas.tsx` (38 paper/doc sources)
- Tests: **49 passed**; frontend production build passes

### Local generative scaffold experiment (TripoSR)
- Added explicit `triposr` engine; it is never part of Auto because its output is inferred
- Runtime is isolated under `%LOCALAPPDATA%\CAD-View`:
  - official TripoSR source
  - isolated Transformers 4.35 packages (VGGT keeps Transformers 5.x)
  - scikit-image Marching Cubes compatibility avoids compiling torchmcubes on Windows
- Best masked view is selected by visibility, centered mask area, border clipping, and sharpness
- Bottle test used `image-0007.jpg`, gray-background masked 512×512 input
- Local RTX 4070 8 GB result at 192³:
  - mesh ID `c41e6347-fc0b-4455-8f46-67c05b588b2f`
  - 34,364 faces, one component, watertight, Euler 0
  - visually cleaner globally than VGGT but inferred a large hollow/recessed back/bottom
- Conclusion: open TripoSR is useful as a hypothesis/scaffold, but it is **not** the proprietary Tripo H3.1 quality and cannot replace measured geometry
- VGGT now explicitly releases CUDA tensors/cache after each job so local models can share the 8 GB GPU
- Tests: **52 passed**; frontend production build passes

### Engines / UI
- `auto` = Meshroom first, VGGT rescue on weak/empty dense result
- Explicit `meshroom` also rescues with VGGT when available
- **Clear result / new capture** clears persisted finished jobs from localStorage

### Capture guidance (small consumer bottle)
- Fill 40–70% of frame, soft light, textured background kept for pose
- 24–36 stills, 60–80% overlap, two elevation rings
- Tight object masks OK (pose uses full frame)

---

## Mesh → SolidWorks (still valid)

Working path: declared units → parametric recipe → .NET bridge / VBS → native feature tree.

Cam groove path when scoring wins:
1. Multi-section PCA slices
2. Orthogonal sweep vs stacked-cut hypothesis
3. Features: mid-plane outer extrude + `InsertCutSwept5` perimeter sweep cut
4. Ambiguous if score delta < 0.03 → do not claim original history

Dev cam STL (local only, gitignored uploads):
`backend/uploads/4d96a6e6-db98-4fc5-9b23-1bdea756a30b.stl`

Cam snapshot (prior session):
- strategy `sweep_cut_reconstruction`, confidence ≈ 0.73
- volume_error ≈ 0.84%, RMS ≈ 0.154 mm
- sweep score ≈ 0.017 vs stacked ≈ 0.166

### SolidWorks notes
- Prefer typed .NET bridge for sweeps (`CreateSpline2` / `InsertCutSwept5`)
- VBS fine for line extrude/cut; unique timestamped `.SLDPRT` names
- Do not reopen from Explorer while SolidWorks still locks the file

### Complex non-prismatic parts
The residual search now retains a bounded beam of three alternative states,
refines all prismatic PCA-axis bases before choosing a winner, and supports
native full-turn `revolve_cut` features on any canonical principal axis.
The mixed regression (base extrusion + boss + annular revolved cut) improved
from a single extrude at IoU 0.8113 to five native features at IoU 0.9985 and
was successfully rebuilt by the SolidWorks .NET bridge.

Still missing: arbitrary-axis revolves, loft/shell/fillet/chamfer/pattern
recovery, native SolidWorks validation during every search expansion, and
general feature deletion/reordering.

---

## Known gaps / next work
1. Persist/view per-face observation confidence and inferred-region masks
2. Interactive hints: protect, erase, local smooth, intentional opening, trim plane, symmetry/axis
3. Improve glossy / low-texture nozzle recovery (MASt3R / Poisson / more views)
4. True Meshroom “scene pose → object densify” robustness on tiny objects
5. Line/arc/spline sketch fitting for base outlines
6. Color deviation overlay in Three.js
7. Fully defined sketches; bidirectional mesh↔CAD deviation
8. Multi-feature decomposition for stepped mechanical parts

---

## Key files
- `backend/reconstruction.py` — Meshroom full-frame SfM + dense masks
- `backend/neural_reconstruction.py` — VGGT + TSDF fusion
- `backend/parametric_reconstruction.py` — editable feature recipes
- `backend/solidworks_bridge/Program.cs` — native SW builder
- `backend/main.py` — API / engine routing
- `frontend/src/App.tsx` — UI, clear session, engine picker
- `backend/tests/test_reconstruction.py`, `test_neural_reconstruction.py`, `test_parametric_reconstruction.py`
- `research/PAPER_LEDGER.md` — reviewed-paper registry and fresh candidate queue;
  check this before every literature search to avoid duplicate papers

## How to resume
1. Backend: `backend\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000`
2. Frontend: `frontend` → `npm run dev -- --host 127.0.0.1 --port 5173`
3. Open http://127.0.0.1:5173
4. Photos: Auto engine, closer capture, Clear result if an old blob is stuck
5. STL: declare units → Analyze editable feature tree → Build SolidWorks part
)
