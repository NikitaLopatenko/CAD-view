# CAD-View resume point (2026-07-27 night)

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
Still fail as single prismatic extrude. Next architecture (research only so far):
mesh regions → surfaces → topology → CSG hypothesis search → SolidWorks tree.
See canvas notes from the complex-part session if needed.

---

## Known gaps / next work
1. Improve glossy / low-texture nozzle recovery (MASt3R / Poisson / more views)
2. True Meshroom “scene pose → object densify” robustness on tiny objects
3. Line/arc/spline sketch fitting for base outlines
4. Color deviation overlay in Three.js
5. Fully defined sketches; bidirectional mesh↔CAD deviation
6. Multi-feature decomposition for stepped mechanical parts

---

## Key files
- `backend/reconstruction.py` — Meshroom full-frame SfM + dense masks
- `backend/neural_reconstruction.py` — VGGT + TSDF fusion
- `backend/parametric_reconstruction.py` — editable feature recipes
- `backend/solidworks_bridge/Program.cs` — native SW builder
- `backend/main.py` — API / engine routing
- `frontend/src/App.tsx` — UI, clear session, engine picker
- `backend/tests/test_reconstruction.py`, `test_neural_reconstruction.py`, `test_parametric_reconstruction.py`

## How to resume
1. Backend: `backend\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000`
2. Frontend: `frontend` → `npm run dev -- --host 127.0.0.1 --port 5173`
3. Open http://127.0.0.1:5173
4. Photos: Auto engine, closer capture, Clear result if an old blob is stuck
5. STL: declare units → Analyze editable feature tree → Build SolidWorks part
)
