# CAD-View

*Photos and meshes in. Editable SolidWorks feature trees out — with honesty about what was measured vs inferred.*

## Inspiration

Anyone who has ever tried to reverse-engineer a physical part knows the painful middle ground: a beautiful mesh that is almost useless for engineering. Photogrammetry and neural reconstruction can give you geometry. SolidWorks wants a history — sketches, extrudes, revolves, cuts — that you can still edit next week when the supplier changes a diameter.

Most “mesh to CAD” tools stop at a dumb solid or a faceted STEP body. Once you import that, you have lost design intent. We wanted the opposite: a pipeline that treats reverse engineering as **qualification**, not magic. Preserve what was observed. Label what was inferred. Recover a parametric feature tree when the evidence supports it, and refuse to overclaim when it does not.

That idea came from watching real parts fail in both directions: a nasal-spray body that looked like an extrude until a scored revolve dropped the volume error from ~48% to ~2%, and mechanical parts where a single global volume score hid shallow grooves and radial holes. CAD-View exists to close that gap between “looks right in the viewer” and “opens as an editable `.SLDPRT`.”

## What it does

CAD-View is a local web app plus geometry API that takes photos, video, or an STL/OBJ/PLY mesh and walks you toward engineering-ready output:

1. **Capture → observed mesh** — Meshroom/AliceVision for classical photogrammetry, with VGGT + masked TSDF fusion as a neural rescue path when dense reconstruction is weak. Foreground masks (SAM 2.1) are reviewed by a human before densification so background furniture does not become part of the part.
2. **Qualify the mesh** — Immutable source storage with SHA-256 provenance, watertightness / winding / component / Euler diagnostics, physical scale from a two-point constraint, and check dimensions with pass/fail tolerances.
3. **Recover editable CAD** — Competing reconstruction hypotheses (prismatic extrude vs revolve about principal axes, cam-style sweep cuts, residual bosses/cuts/radial holes, revolved cuts) are scored against the mesh. Winners compile into a native SolidWorks feature tree through a typed .NET bridge (with VBScript fallbacks for simpler ops).
4. **Export with receipts** — Download qualified meshes, STEP (analytic or faceted), SolidWorks scripts/parts, and machine-readable quality reports that say what agreed and what was left as residual.

In short: not just “AI made a 3D model,” but “here is a SolidWorks part you can edit, and here is how confident we are.”

## How we built it

**Frontend.** React + Three.js viewer for inspection, scale picking, mask review, engine selection, and export actions. The UI stays close to the geometry: you see the mesh, the hypothesized solid, and the residual regions rather than a black-box progress bar.

**Backend.** FastAPI orchestration over a Python geometry stack (NumPy / SciPy / trimesh / CadQuery–OpenCascade) for diagnostics, solid agreement metrics, and parametric recipe search. Photo jobs call Meshroom; neural jobs call VGGT with confidence-masked TSDF fusion so CUDA memory can be shared with optional local scaffold models.

**Parametric search.** For a scaled mesh we build multiple hypotheses — for example revolve vs extrude about each PCA axis — refine parameters, and score volume agreement plus local surface residual. A residual loop then proposes additional features (bosses, cuts, radial holes, `revolve_cut`) under a bounded beam search so mixed histories are possible, not only a single primitive.

A typical selection objective combines global overlap with complexity control. Writing the volume IoU as

$$
\mathrm{IoU}(A,B)=\frac{|A\cap B|}{|A\cup B|}
$$

we still gate acceptance of an extra feature by a minimum local improvement, because a part can sit at $\mathrm{IoU}\approx 0.97$ while still missing a hole that matters to manufacturing.

**SolidWorks handoff.** Accepted recipes compile to sketch + feature operations executed by a C# COM bridge (`FeatureExtrusion`, revolves, sweep cuts, hole cuts). The deliverable is a timestamped `.SLDPRT` with an editable tree, not a silent import of triangles.

**Research discipline.** Mesh-to-CAD literature is noisy and often mis-cited. We keep a paper ledger so every architectural bet (segmentation, residual scoring, native-kernel validation) maps to verified sources — and so we do not reinvent CADENA/CADReasoner-style loops under a new name.

## Challenges we ran into

- **Measurement vs inference.** Neural meshes can look watertight while still inventing hollows or erasing glossy regions. We had to separate observed reconstruction from generative scaffolds and force human review of masks and scale.
- **Global scores lie.** High volume IoU can reject shallow grooves and thin radial holes. The spool case that “wins” as a single revolve at ~96.6% IoU still misses circumferential detail that a human sees immediately.
- **Search geometry ≠ CAD kernel geometry.** A cylinder that scores well as a 3D boolean can fail in SolidWorks when the exporter maps it to the wrong sketch plane or cut axis — producing under-defined sketches or rejected features.
- **Feature vocabulary is unfinished.** Domes become extrudes; fillets and patterns are not yet first-class operations; residual depth is bounded. Real mechanical parts outrun a short action set.
- **Windows CAD automation.** Sharing a GPU between vision models, keeping SolidWorks file locks honest, and making COM/VBS builds reproducible under real licenses is unglamorous and mandatory.

## Accomplishments that we're proud of

- An end-to-end path from **photos or STL → qualified mesh → editable SolidWorks history** on a local machine.
- Hypothesis competition that correctly prefers a **revolve** for axisymmetric consumer parts instead of a bad default extrude (demo: ~48% → ~2% volume error).
- Mixed-history residual reconstruction that recovered a synthetic **extrude + boss + annular revolved cut** tree and rebuilt it natively in SolidWorks at near-perfect IoU.
- Provenance-first design: immutable sources, explicit unscaled photogrammetry labels, and quality reports instead of silent mesh surgery.
- A research ledger that keeps the roadmap honest about what papers actually solve versus what is still engineering work (frames, rollback, local scoring).

## What we learned

- Reverse engineering is a **search + validation** problem, not a single network call. Geometry agreement, topology, and native rebuild failures all have to vote.
- Photogrammetry still needs classical craft: overlap, lighting, masks applied at the right stage, and scale anchors before any dimensional claim.
- Editable CAD means speaking the kernel’s language — sketch planes, merge flags, body counts — not only approximating solids in Python.
- Literature helps most when you ask narrow questions (intersecting primitive segmentation, local residual objectives). Broad “CAD generation” papers rarely fix the failure on your desk.
- Shipping a demable `.SLDPRT` forces better product decisions than optimizing a leaderboard metric alone.

## What's next for CAD-View

- **Local residual objectives** so small holes and shallow grooves are not drowned by global IoU.
- **Primitive-aware segmentation** (cylinder / torus / hole patches) to propose features humans already see.
- **Complete SolidWorks frames** (origin + orthonormal basis), per-feature rollback, and scoring against the native rebuild — not only the manifold approximation.
- Broader operations: local revolves/domes, fillets/chamfers, and circular/linear patterns for repeated bosses and holes.
- Richer scan UX: confidence overlays, protect/erase regions, and clearer separation of observed vs inferred surfaces.
- Longer-horizon beam search with deletion/reordering so complex mechanical trees stay editable instead of collapsing to a single best solid.

CAD-View’s north star stays the same: geometry you can trust, history you can edit, and silence where the evidence is not there yet.
