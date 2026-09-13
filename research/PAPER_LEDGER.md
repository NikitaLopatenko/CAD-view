# CAD-View Literature Ledger

Last updated: 2026-09-13

This file prevents repeated literature reviews. Check it before searching for
new papers. A paper is considered a duplicate when its normalized title or
DOI/arXiv identifier matches an existing entry, even if the supplied year or
author list differs.

## Status definitions

- **FULL_TEXT_REVIEWED**: The complete local or authoritative online text was
  read and its methods were evaluated against CAD-View.
- **PARTIALLY_REVIEWED**: The citation, accessible text, or reported method was
  examined, but a reliable local full-text PDF was not reviewed.
- **QUEUED_UNVERIFIED**: Suggested as potentially relevant. Its existence,
  bibliographic metadata, technical claims, and accessibility have not yet
  been independently verified.
- **REJECTED**: Examined and found irrelevant, inaccessible, or otherwise
  unsuitable. Record the reason instead of deleting the entry.

## Already reviewed in full

Do not include these in a future "find fresh papers" search unless the task is
explicitly to revisit or compare previously reviewed work.

1. **CADENA: Stepwise CAD Reverse Engineering** — Kabisov et al. (2026)
   - Status: **FULL_TEXT_REVIEWED**
   - Local file: `mesh-to-cad-papers/01-CADENA-2026.pdf`
   - Previously considered for: stepwise residual-conditioned reconstruction,
     executable CAD operations, and geometric feedback.

2. **CADReasoner: Iterative Program Editing for CAD Reverse Engineering** —
   Kabisov et al. (2026)
   - Status: **FULL_TEXT_REVIEWED**
   - Local file: `mesh-to-cad-papers/02-CADReasoner-2026.pdf`
   - Previously considered for: iterative code editing, geometric residuals,
     and alternative feature-tree search.

3. **cadrille: Multi-modal CAD Reconstruction with Online Reinforcement
   Learning** — Kolodiazhnyi et al. (2025)
   - Status: **FULL_TEXT_REVIEWED**
   - Local file: `mesh-to-cad-papers/03-cadrille-2025.pdf`
   - Metadata note: the new candidate list called this a 2026 paper; the
     reviewed local copy is labeled 2025.
   - Previously considered for: geometry-rewarded reinforcement learning and
     resolving equivalent CAD programs without token-level matching.

4. **CAD-Recode: Reverse Engineering CAD Code from Point Clouds** (2025 local
   filename)
   - Status: **FULL_TEXT_REVIEWED**
   - Local file: `mesh-to-cad-papers/04-CAD-Recode-2025.pdf`
   - Previously considered for: point-cloud-to-CadQuery generation, procedural
     training data, execution rate, and single-pass sequence failures.

5. **GenCAD-3D** (2025)
   - Status: **FULL_TEXT_REVIEWED**
   - Local file: `mesh-to-cad-papers/05-GenCAD-3D-2025.pdf`
   - Previously considered for: multimodal latent alignment, parameter
     perturbation, and complex CAD-sequence generation.

6. **Point2CAD: Reverse Engineering CAD Models from 3D Point Clouds** (2024)
   - Status: **FULL_TEXT_REVIEWED**
   - Local file: `mesh-to-cad-papers/06-Point2CAD-2024.pdf`
   - Previously considered for: surface segmentation, primitive fitting,
     intersection, and B-Rep reconstruction.

7. **DeepCAD: A Deep Generative Network for Computer-Aided Design Models**
   (2021)
   - Status: **FULL_TEXT_REVIEWED**
   - Local file: `mesh-to-cad-papers/07-DeepCAD-2021.pdf`
   - Previously considered for: autoregressive CAD sequences, token
     representations, and canonical-history ambiguity.

8. **SkexGen: Autoregressive Generation of CAD Construction Sequences** (2022)
   - Status: **FULL_TEXT_REVIEWED**
   - Local file: `mesh-to-cad-papers/08-SkexGen-2022.pdf`
   - Metadata note: author attribution in newly supplied summaries must be
     checked against the PDF rather than assumed.
   - Previously considered for: separated topology/geometry generation and
     sketch-extrude construction sequences.

9. **Point2Cyl: Reverse Engineering 3D Objects from Point Clouds to Extrusion
   Cylinders** (2022)
   - Status: **FULL_TEXT_REVIEWED**
   - Local file: `mesh-to-cad-papers/09-Point2Cyl-2022.pdf`
   - Previously considered for: extrusion-cylinder decomposition, axis
     estimation, and localized primitive recovery.

## Previously examined without a reliable local PDF

1. **InverseCSG: Automatic Conversion of 3D Models to CSG Trees** — Du et al.
   (2018)
   - Status: **PARTIALLY_REVIEWED**
   - Access note: automated PDF downloads returned HTML or were blocked. The
     citation and accessible online material were examined.
   - Previously considered for: zone graphs, Boolean program synthesis, and
     minimum-description-length handling of equifinality.

## Candidate set reviewed on 2026-09-13

All eleven supplied candidates were checked against authoritative records and
their available full text. Several supplied titles, years, or author
attributions were incorrect; corrected metadata is recorded below.

### CAD vocabulary and complex-history testing

1. **CADEvolve: Creating Realistic CAD via Program Evolution** — Maksim
   Elistratov et al. (2026), arXiv:2602.16317
   - Status: **FULL_TEXT_REVIEWED**
   - Sources: <https://arxiv.org/abs/2602.16317>,
     <https://github.com/zhemdi/CADEvolve>
   - Verdict: **high value and non-redundant** for expanding the operation
     grammar and creating mixed-history training/regression data.
   - Evidence: evolves 46 CadQuery generators into 7,945 validated generators
     spanning extrude, revolve, loft, sweep, shell, fillet, chamfer, booleans,
     and patterns; produces 2.72M canonicalized scripts.
   - Limitation: synthetic CadQuery histories and multi-view image input do not
     directly solve mesh-to-SolidWorks reconstruction or native feature
     reference stability.

2. **Text2CAD-Bench: A Benchmark for LLM-based Text-to-Parametric CAD
   Generation** — Liang Wang et al. (2026), arXiv:2605.18430
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://arxiv.org/abs/2605.18430>
   - Metadata correction: not authored by Yavartanoo et al.
   - Verdict: **useful later as a testing framework, not a reconstruction
     method**.
   - Evidence: 600 examples across four complexity levels; L3 includes sweep,
     loft, shell, patterns, and path-based geometry.
   - Limitation: text-to-CAD, partial public benchmark, and no per-operation
     reverse-engineering method.

### Long-horizon search and execution-guided synthesis

3. **Write, Execute, Assess: Program Synthesis with a REPL** — Kevin Ellis et
   al. (NeurIPS 2019), arXiv:1906.04604
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://arxiv.org/abs/1906.04604>
   - Metadata correction: 2019, not 2024.
   - Verdict: **conceptually useful but mostly superseded for CAD by
     CADReasoner**.
   - Evidence: maintains and resamples multiple executable partial programs
     using Sequential Monte Carlo and learned value estimates.
   - Limitation: restricted voxel CSG grammar, not B-Rep/feature-history CAD,
     no native CAD-kernel validation, and weak protection of thin features.

### Native/differentiable evaluation and small features

4. **DreamCAD: Scaling Multi-modal CAD Generation using Differentiable
   Parametric Surfaces** — Mohammad Sadil Khan et al. (ECCV 2026),
   arXiv:2603.05607
   - Status: **REJECTED** for the stated CAD-View problems after full-text review.
   - Source: <https://arxiv.org/abs/2603.05607>
   - Metadata correction: no authoritative paper with the supplied
     "Differentiable CSG" title was found; the identifiable paper uses rational
     Bézier patches, not CSG.
   - Reason: generates tessellated patch surfaces and incomplete STEP topology,
     not sketches, constraints, operations, or editable feature histories.

5. **DiffCSG: Differentiable CSG via Rasterization** — Haocheng Yuan et al.
   (SIGGRAPH Asia 2024), arXiv:2409.01421
   - Status: **FULL_TEXT_REVIEWED**
   - Sources: <https://arxiv.org/abs/2409.01421>,
     <https://github.com/YYYYYHC/Differentiable-CSG-via-Rasterization>
   - Metadata correction: Laine et al. are not the authors; their Nvdiffrast
     system is extended by this paper.
   - Verdict: **medium value for continuous parameter refinement after a
     discrete tree is already selected**.
   - Limitation: assumes known CSG structure and primitive types, bypasses
     Boolean kernels, and cannot discover operations or guarantee native CAD
     validity.

6. **DualPrim: Compact 3D Reconstruction with Positive and Negative
   Primitives** — Xiaoxu Meng et al. (CVPR 2026), arXiv:2603.16133
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://arxiv.org/abs/2603.16133>
   - Metadata correction: not Wang et al.; the omitted method name is DualPrim.
   - Verdict: **medium value as inspiration for positive/negative residual
     proposals, low value as an output representation**.
   - Limitation: outputs superquadric-derived meshes rather than editable CAD,
     assumes multi-view fitting, and misses structures below voxel resolution.

### Feature order and design intent

7. **SOV-CAD: Stepwise Orthographic Views Guided CAD Modeling Sequence
   Reconstruction** — Zhaopeng Feng et al. (2026), arXiv:2607.04119
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://arxiv.org/abs/2607.04119>
   - Metadata correction: "Phong et al." was incorrect.
   - Verdict: **useful orthographic-state idea, but substantially overlaps
     CADENA/CADReasoner's execute-measure-continue loop**.
   - Distinct insight: compare target/current orthographic renders and the
     active sketch while choosing the next operation.
   - Limitation: incomplete released implementation, synthetic evaluation, and
     no guarantee of original feature order or design intent.

8. **Text2CAD: Generating Sequential CAD Designs from Beginner-to-Expert Level
   Text Prompts** — Mohammad Sadil Khan et al. (NeurIPS 2024)
   - Status: **FULL_TEXT_REVIEWED**
   - Source:
     <https://proceedings.neurips.cc/paper_files/paper/2024/hash/0e5b96f97c1813bb75f6c28532c2ecc7-Abstract-Conference.html>
   - Metadata correction: not Yavartanoo et al.; that team published a
     different Text2CAD paper.
   - Verdict: **low priority and largely redundant** with
     DeepCAD/SkexGen/CAD-Recode for reverse engineering.
   - Limitation: text-conditioned sketch/extrude generation cannot infer
     feature order or original intent from a mesh.

### Sketch constraints and noisy meshes

9. **SketchGen: Generating Constrained CAD Sketches** — Wamiq Reyaz Para et al.
   (NeurIPS 2021)
   - Status: **FULL_TEXT_REVIEWED**
   - Source:
     <https://proceedings.neurips.cc/paper/2021/hash/28891cb4ab421830acc36b1f5fd6c91e-Abstract.html>
   - Verdict: **high value and non-redundant for cleaning residual sketches**.
   - Evidence: separate primitive/constraint Transformers, pointer references,
     and an Onshape constraint solver; reported 98.4% constraint accuracy on
     perturbed test sketches.
   - Limitation: no guarantee of a fully defined sketch, restricted primitive
     and constraint vocabulary, and no sequence backtracking.

10. **OpenECAD: An Efficient Visual Language Model for Editable 3D-CAD
    Design** — Zhe Yuan, Jianqi Shi, Yanhong Huang (2024)
    - Status: **FULL_TEXT_REVIEWED**
    - Source: <https://arxiv.org/abs/2406.09913>
    - Metadata correction: not Chen et al.; the final journal title differs
      from the supplied title.
    - Verdict: **reuse DSL/sketch-plane validation concepts only**.
    - Limitation: single-image generation, frequent wrong later sketch planes
      and missing features, with no demonstrated fully constrained sketches or
      incremental geometric feedback.

11. **CADDreamer: CAD Object Generation from Single-view Images** — Yuan Li et
    al. (CVPR 2025)
    - Status: **FULL_TEXT_REVIEWED**
    - Source:
      <https://openaccess.thecvf.com/content/CVPR2025/html/Li_CADDreamer_CAD_Object_Generation_from_Single-view_Images_CVPR_2025_paper.html>
    - Metadata correction: not Gao et al.
    - Verdict: **high architectural value for relation-aware primitive fitting,
      but not a direct arbitrary-mesh repair solution**.
    - Evidence: fits planes, cylinders, cones, spheres, and tori; recovers
      parallel/perpendicular/collinear relations; jointly stitches primitives.
    - Limitation: assumes topology from its internally reconstructed watertight
      mesh and outputs B-Rep surfaces, not an editable feature tree.

## Candidate set reviewed on 2026-09-13 (second batch)

### Native CAD execution and judging

1. **ComAct: Reframing Professional Software Manipulation via COM-as-Action
   Paradigm** — Jiaxin Ai et al. (2026), arXiv:2606.13239
   - Status: **FULL_TEXT_REVIEWED**
   - Sources: <https://arxiv.org/abs/2606.13239>,
     <https://github.com/KnowledgeXLab/ComAct>
   - Verdict: **high value and non-redundant** for native SolidWorks/Inventor/
     AutoCAD execution infrastructure.
   - Actual contribution: Qwen-based agents generate and execute Python COM
     scripts in isolated Windows environments; complete artifacts receive
     Chamfer-based GRPO reward.
   - Important correction: it does not implement atomic COM transactions,
     prefix-level competing feature trees, rollback through native undo, or
     topology-stable references. CAD-View must build those pieces.

2. **CAD-Judge: Toward Efficient Morphological Grading and Verification for
   Text-to-CAD Generation** — Zheyuan Zhou et al. (ICASSP 2026),
   arXiv:2508.04002
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://arxiv.org/abs/2508.04002>
   - Verdict: **low incremental value; substantially mischaracterized**.
   - Actual contribution: a rule-based PythonOCC compile/tessellate/Chamfer
     judge generates binary preferences for KTO; it is not a learned native
     feature-tree validity model.
   - Useful fragment: compiler failure taxonomy and structured retry loop.

3. **CAD-Coder: Text-to-CAD Generation with Chain-of-Thought and Geometric
   Reward** — Yandong Guan et al. (NeurIPS 2025), arXiv:2505.19713
   - Status: **FULL_TEXT_REVIEWED**
   - Sources: <https://arxiv.org/abs/2505.19713>,
     <https://github.com/gudo7208/CAD-Coder>
   - Verdict: **mostly redundant** with cadrille/CADReasoner for CAD-View.
   - Actual contribution: complete CadQuery scripts receive OpenCascade
     execution and Chamfer-based GRPO reward; no partial-tree execution or
     mesh-conditioned reverse engineering.
   - Naming warning: a separate paper with the same name by Anna C. Doris et
     al., arXiv:2505.14646, is image-to-CadQuery.

### Long-horizon and mixed-operation generation

4. **ReACT: Reward-informed Autoregressive Decision CAD Transformer** — Yijie
   Ding et al. (AAAI 2026), DOI:10.1609/aaai.v40i5.37360
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://ojs.aaai.org/index.php/AAAI/article/view/37360>
   - Verdict: **medium architectural value, but mostly covered** by
     CADENA/CADReasoner/cadrille.
   - Distinct idea: Local Barrel Point scaffolds and return-conditioned offline
     sequence learning.
   - Limitation: sketch/extrude only, one autoregressive trajectory, no beam,
     rollback, deletion, reordering, revolve, sweep, loft, or fillet.

5. **RLCAD: Reinforcement learning training gym for revolution involved CAD
   command sequence generation** — Xiaolong Yin et al. (*Computer-Aided
   Design* 192, 2026), DOI:10.1016/j.cad.2025.104027
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://arxiv.org/abs/2503.18549>
   - Verdict: **high value for native-kernel gym architecture; medium direct
     reconstruction value**.
   - Actual contribution: parallel Parasolid environments, mark-and-revert,
     PPO, and extrude/revolve actions extracted from exact target B-Rep faces.
   - Limitation: target B-Rep oracle, narrow grammar, per-target training, no
     arbitrary STL input, top-k beam, fillet, sweep, loft, shell, or pattern.

6. **VQ-CAD** — Hanxiao Wang et al. (*Computer Aided Geometric Design* 111,
   2024), DOI:10.1016/j.cagd.2024.102327
   - Status: **REJECTED** for CAD-View reconstruction after full-text review.
   - Source: <https://weizequan.github.io/2024/CAGD/VQ-CAD.pdf>
   - Metadata correction: 2024, not 2025/2026.
   - Reason: diffusion generates DeepCAD-style sketch/extrude programs without
     target 3D geometry, kernel feedback, corrective search, or backtracking.

7. **CAD-MLLM: Multimodal Large Language Model for CAD Generation** — Jingwei
   Xu et al. (2024), arXiv:2411.04954
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://arxiv.org/abs/2411.04954>
   - Verdict: **medium dataset/pretraining value, low search value**.
   - Corrections: not a 2026 paper; data include normals rather than arbitrary
     unoriented scans; implemented grammar is sketch/extrude only and excludes
     revolve, fillet, chamfer, sweep, loft, shell, and pattern.

8. **CADmium** — Prashant Govindarajan et al. (TMLR 2026),
   arXiv:2507.09792
   - Status: **REJECTED** for geometric reverse engineering after full-text
     review.
   - Source: <https://arxiv.org/abs/2507.09792>
   - Reason: text-to-JSON sketch/extrude generation with greedy decoding; no
     mesh input, broad grammar, kernel feedback, alternatives, or backtracking.

### Executable datasets and constraint-aware histories

9. **FllumaOne: A Code-Native Multimodal CAD Dataset with Executable Programs
   and Kernel-Validated Feature Histories** — Jizong Zhan (2026),
   arXiv:2606.17696
   - Status: **FULL_TEXT_REVIEWED**
   - Sources: <https://arxiv.org/abs/2606.17696>,
     <https://github.com/Cad-Kernel/FllumaOne-100K>
   - Verdict: **medium-high value as OpenCascade-validated mixed-operation
     training and regression data**.
   - Evidence: 100,000 procedural samples, 53 template families, 44 model
     tokens, maximum 11 features, and STEP write/reload checks.
   - Limitation: demonstrated model is text-to-program; no mesh/history
     recovery, equifinality model, thin-feature objective, or damaged inputs.

10. **HistCAD: A Constraint-Aware Parametric History-Based CAD
    Representation, Dataset, and Benchmark with Industrial Complexity** —
    Xintong Dong et al. (2026 v2), arXiv:2602.19171
    - Status: **FULL_TEXT_REVIEWED**
    - Source: <https://arxiv.org/abs/2602.19171>
    - Verdict: **high value for CAD-View's target schema and editability tests;
      low evidence for intent recovery**.
    - Evidence: explicit geometric/dimensional constraints and extrude,
      revolve, helix sweep, fillet, and chamfer histories; evaluates parameter
      edit success.
    - Correction: it preserves supplied histories/constraints; it does not
      infer original datums, constraints, or order from final geometry and does
      not model equifinality.

### Noisy meshes and feature-preserving preprocessing

11. **Adaptive Convex Decompositions for Robust Surface Reconstruction**
    (claimed 2025/2026)
    - Status: **REJECTED**
    - Reason: no authoritative publication matches this exact title. The claim
      conflates multiple convex decomposition and residual primitive papers.
    - Closest reviewed work, *Learning Convex Decomposition via Feature
      Fields* (CVPR 2026), creates convex-hull proxies for collision/simulation,
      not topology repair, analytic CAD, or feature histories, and is weak on
      incomplete geometry and thin structures.

12. **A framework from point clouds to workpieces** — Li-Yong Shen et al.
    (2022), DOI:10.1186/s42492-022-00117-0
    - Status: **FULL_TEXT_REVIEWED**
    - Source: <https://pmc.ncbi.nlm.nih.gov/articles/PMC9395558/>
    - Verdict: **low value for editable CAD; useful context for machining
      preprocessing**.
    - Actual pipeline: IGR watertight reconstruction, MeshTGV denoising,
      QuadriFlow, sharp-edge segmentation, B-spline patches, and CNC paths.
    - Limitation: does not infer analytic features, intentional openings,
      uncertainty, constraints, or feature history.

13. **Mesh Total Generalized Variation for Denoising** — Zheng Liu et al.
    (IEEE TVCG, online 2021 / issue 2022)
    - Status: **FULL_TEXT_REVIEWED**
    - Sources: <https://doi.org/10.1109/TVCG.2021.3088118>,
      <https://github.com/LabZhengLiu/MeshTGV>
    - Verdict: **medium value as optional feature-preserving denoising before
      surface analysis**.
    - Limitation: assumes fixed valid triangulated topology, cannot infer
      missing topology, and can erase features smaller than the noise scale.

### Persistent/topological naming

14. **A Lineage-Based Referencing DSL for Computer-Aided Design** — Dan
    Cascaval, Rastislav Bodik, Adriana Schulz (PLDI 2023),
    DOI:10.1145/3591223
    - Status: **FULL_TEXT_REVIEWED**
    - Sources: <https://par.nsf.gov/servlets/purl/10461767>,
      <https://github.com/dcascaval/lineage-based-cad-referencing>
    - Verdict: **high value, non-redundant architectural reference**.
    - Actual contribution: explicit provenance graphs and declarative queries
      over subset/transform/derivation lineage, with ambiguity and missing
      references failing explicitly.
    - Limitation: custom 2.5D research kernel without general solid booleans or
      direct SolidWorks/OpenCascade integration.

15. **An Approach to Persistent Naming and Naming Mapping Based on OSI and IGM
    for Parametric CAD Model Exchanges** — Duhwan Mun, Soonhung Han (2004)
    - Status: **FULL_TEXT_REVIEWED**
    - Source:
      <http://koreascience.or.kr/article/JAKO200413842032898.page>
    - Metadata correction: 2004, not 2026.
    - Verdict: **medium historical value** for provenance plus geometric
      fallback across systems.
    - Limitation: worked examples rather than completed evaluation; OSI
      ordering is fragile under symmetry and coordinate/topology changes.

16. **Learning-based 3D CAD model generation in mechanical engineering: A
    survey** — Fabian Baumeister et al. (*Advanced Engineering Informatics*
    76, 2026), DOI:10.1016/j.aei.2026.104990
    - Status: **FULL_TEXT_REVIEWED**
    - Source: <https://publikationen.bibliothek.kit.edu/1000194899>
    - Verdict: **mostly redundant; useful only as independent gap
      confirmation**.
    - Correction: persistent naming receives only brief coverage; the paper
      introduces no naming algorithm or native-kernel solution.

## Candidate set reviewed on 2026-09-13 (third batch)

The supplied “CAD-View Fix” statements below were treated as hypotheses, not
paper results. None of these papers directly reconstructs an editable
SolidWorks feature history from an STL.

### Primitive and surface segmentation

1. **HPNet: Deep Primitive Segmentation Using Hybrid Representations** —
   Siming Yan et al. (ICCV 2021), DOI:10.1109/ICCV48922.2021.00275,
   arXiv:2105.10620
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://openaccess.thecvf.com/content/ICCV2021/html/Yan_HPNet_Deep_Primitive_Segmentation_Using_Hybrid_Representations_ICCV_2021_paper.html>
   - Verdict: **high-value adaptable proposal generator**.
   - Actual contribution: point-cloud primitive segmentation using learned,
     parameter-consistency, and sharp-edge descriptors with spectral
     clustering. Classes include planes, spheres, cylinders, cones, and
     B-splines, but not tori or CAD operations.
   - CAD-View decision: strongest candidate to prototype on sampled STL
     points/normals for radial-hole cylinders and small patch boundaries. It
     cannot by itself complete a cylinder or recover a feature tree.

2. **ParSeNet: A Parametric Surface Fitting Network for 3D Point Clouds** —
   Gopal Sharma et al. (ECCV 2020), DOI:10.1007/978-3-030-58571-6_16,
   arXiv:2003.12181
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://link.springer.com/chapter/10.1007/978-3-030-58571-6_16>
   - Verdict: **high-value adaptable surface fitter**.
   - Actual contribution: segments and fits planes, spheres, cones, cylinders,
     and open/closed cubic B-spline patches from point clouds. “Editable”
     refers to patch parameters, not construction history.
   - CAD-View decision: useful for bounded cylinders and patch boundaries, but
     does not force radial holes to detach, infer booleans, or support tori.

3. **BRepNet: A Topological Message Passing System for Solid Models** —
   Joseph G. Lambourne et al. (CVPR 2021),
   DOI:10.1109/CVPR46437.2021.01258
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://openaccess.thecvf.com/content/CVPR2021/html/Lambourne_BRepNet_A_Topological_Message_Passing_System_for_Solid_Models_CVPR_2021_paper.html>
   - Verdict: **low immediate value; wrong pipeline stage**.
   - Correction: labels faces on an already existing B-Rep using
     face/edge/co-edge topology. It cannot run on the input STL to find spool
     holes and is only a possible downstream native-output validator.

4. **UV-Net: Learning from Boundary Representations** — Pradeep Kumar
   Jayaraman et al. (CVPR 2021), DOI:10.1109/CVPR46437.2021.01153,
   arXiv:2006.10211
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://openaccess.thecvf.com/content/CVPR2021/html/Jayaraman_UV-Net_Learning_From_Boundary_Representations_CVPR_2021_paper.html>
   - Verdict: **low immediate value; wrong pipeline stage**.
   - Correction: encodes parameterized UV grids and adjacency from an existing
     B-Rep for classification/retrieval. It does not flatten an STL cylinder or
     turn its grooves into recovered revolve-cut operations.

5. **DefeatureNet: A Deep-Learning Framework for the Removal of CAD Model
   Features** (claimed 2021)
   - Status: **REJECTED**
   - Reason: no authoritative publication matching this title and claimed
     method was found. Do not treat “inverting its segmentation weights” as an
     implementation direction without a verifiable source.
   - Possible conflation: *FeatureNet: Machining Feature Recognition Based on
     3D Convolution Neural Network* (Zhang, Jaiswal, Rai, CAD 2018),
     DOI:10.1016/j.cad.2018.03.006; that work is also not the claimed
     defeaturing/history-reconstruction method.

### Local and topology-sensitive representations

6. **Local Deep Implicit Functions for 3D Shape** — Kyle Genova et al.
   (CVPR 2020), arXiv:1912.06126
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://openaccess.thecvf.com/content_CVPR_2020/html/Genova_Local_Deep_Implicit_Functions_for_3D_Shape_CVPR_2020_paper.html>
   - Verdict: **low direct value for the current acceptance gate**.
   - Correction: LDIF is a learned shape representation made from overlapping
     local implicit functions, not a local IoU metric or drop-in residual gate.
     It ultimately returns mesh geometry and reports difficulty with thin
     structures.
   - CAD-View decision: implement deterministic local residual scoring first;
     LDIF is not required for that engineering change.

7. **Topology-Aware Surface Reconstruction for Point Clouds** — Rickard
   Brüel-Gabrielsson et al. (*Computer Graphics Forum* 39(5), 2020),
   DOI:10.1111/cgf.14079, arXiv:1811.12543
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://diglib.eg.org/items/dea95bfc-21bd-46b8-a123-18e137a607d1>
   - Metadata correction: 2020, not CVPR 2022.
   - Verdict: **medium conceptual value for a topology gate**.
   - Actual contribution: surface reconstruction constrained by supplied
     Betti-number / persistent-homology priors; it does not infer the desired
     topology or machining feature.
   - CAD-View decision: test topology-change terms only alongside local
     geometric evidence. A genus penalty alone cannot determine the intended
     count or placement of radial holes.

8. **Neural-Pull: Learning Signed Distance Functions from Point Clouds by
   Learning to Pull Space onto Surfaces** — Baorui Ma et al. (ICML 2021),
   arXiv:2011.13495
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://proceedings.mlr.press/v139/ma21b.html>
   - Verdict: **low direct value for these watertight STL inputs**.
   - Correction: learns a per-shape SDF from raw points through nearest-surface
     pulling, then extracts a mesh. It neither specifically preserves shallow
     grooves nor replaces boolean scoring with analytic CAD features.

### Partial geometry and feature completion

9. **PIE-NET: Parametric Inference of Point Cloud Edges** — Xiaogang Wang et
   al. (NeurIPS 2020), arXiv:2007.04883
   - Status: **FULL_TEXT_REVIEWED**
   - Source: <https://proceedings.neurips.cc/paper/2020/hash/e94550c93cd70fe748e6982b3439ad3b-Abstract.html>
   - Verdict: **high-value adaptable boundary evidence**.
   - Actual contribution: detects sharp feature edges and fits line, circle,
     and B-spline curve parameters. It does not reconstruct surfaces, solids,
     missing features, or histories.
   - CAD-View decision: evaluate circle/edge fitting as evidence for fragmented
     hole and groove proposals; completion and operation inference remain ours.

10. **ExtrudeNet: Unsupervised Inverse Sketch-and-Extrude for Shape Parsing**
    — Daxuan Ren et al. (ECCV 2022),
    DOI:10.1007/978-3-031-20086-1_28, arXiv:2209.15632
    - Status: **FULL_TEXT_REVIEWED**
    - Source: <https://www.ecva.net/papers/eccv_2022/papers_ECCV/html/194_ECCV_2022_paper.php>
    - Verdict: **high-value representation/reference for extruded details**.
    - Actual contribution: unsupervised point-cloud parsing into rational
      Bézier sketch extrusions combined by CSG-like booleans.
    - CAD-View decision: useful for bosses, through-holes, and grooves that are
      true extrudes; it cannot recover revolved grooves, domes, or fillets.

11. **ComplexGen: CAD Reconstruction by B-Rep Chain Complex Generation** —
    Haoxiang Guo et al. (ACM TOG 41(4), SIGGRAPH 2022),
    DOI:10.1145/3528223.3530078, arXiv:2205.14573
    - Status: **FULL_TEXT_REVIEWED**
    - Source: <https://arxiv.org/abs/2205.14573>
    - Verdict: **high geometric value, medium history value**.
    - Actual contribution: jointly infers B-Rep vertices, curves, surfaces, and
      topology from point clouds, then optimizes consistency; supports tori and
      spheres in addition to common analytic surfaces.
    - CAD-View decision: valuable reference for completing fragmented loops,
      domes, toroidal grooves, and face incidence. It outputs a B-Rep, not an
      ordered editable feature history.

### Symmetry and repetition

12. **JoinABLe: Learning Bottom-Up Assembly of Parametric CAD Joints** — Karl
    D. D. Willis et al. (CVPR 2022), DOI:10.1109/CVPR52688.2022.01539,
    arXiv:2111.12772
    - Status: **FULL_TEXT_REVIEWED**
    - Source: <https://openaccess.thecvf.com/content/CVPR2022/html/Willis_JoinABLe_Learning_Bottom-Up_Assembly_of_Parametric_CAD_Joints_CVPR_2022_paper.html>
    - Verdict: **REJECTED for within-part pattern recovery**.
    - Correction: predicts joints and relative poses between pairs of existing
      B-Rep parts. It does not group repeated bosses/holes inside one STL and
      does not imply a SolidWorks circular pattern.

13. **SymmetryNet: Learning to Predict Reflectional and Rotational Symmetries
    of 3D Shapes from Single-View RGB-D Images** — Yifei Shi et al. (ACM TOG
    39(6), SIGGRAPH Asia 2020), DOI:10.1145/3414685.3417775,
    arXiv:2008.00485
    - Status: **FULL_TEXT_REVIEWED**
    - Source: <https://gfx.cs.princeton.edu/pubs/Shi_2020_SLT/index.php>
    - Metadata correction: SIGGRAPH Asia, not CVPR.
    - Verdict: **medium-low, indirect value**.
    - Correction: predicts global symmetry planes and axes from segmented
      single-view RGB-D. It does not detect discrete repetition count or
      consume an STL directly.
    - CAD-View decision: simpler deterministic rotational/reflective clustering
      around the already estimated CAD axis is the better first implementation.

### Broader geometric vocabulary

14. **SolidGen: An Autoregressive Model for Direct B-rep Synthesis** — Pradeep
    Kumar Jayaraman et al. (TMLR 2023), arXiv:2203.13944
    - Status: **FULL_TEXT_REVIEWED**
    - Source: <https://openreview.net/forum?id=ZR2CDgADRo>
    - Metadata correction: archival publication is 2023; 2022 is the preprint.
    - Verdict: **low direct reconstruction value; medium B-Rep-prior value**.
    - Correction: directly generates B-Rep topology/geometry, including
      conditioned samples, but does not infer construction sequences. It cannot
      classify palm domes into SolidWorks operations as claimed.

15. **CSG-Stump: A Learning Friendly CSG-Like Representation for Interpretable
    Shape Parsing** — Daxuan Ren et al. (ICCV 2021),
    DOI:10.1109/ICCV48922.2021.01225, arXiv:2108.11305
    - Status: **FULL_TEXT_REVIEWED**
    - Source: <https://openaccess.thecvf.com/content/ICCV2021/html/Ren_CSG-Stump_A_Learning_Friendly_CSG-Like_Representation_for_Interpretable_Shape_Parsing_ICCV_2021_paper.html>
    - Verdict: **medium adaptable value for coarse compound primitives**.
    - Actual contribution: unsupervised point-cloud decomposition into boxes,
      spheres, cylinders, and cones using a fixed complement/intersection/union
      expression.
    - CAD-View decision: useful inspiration for cylinder+sphere domed bosses,
      but weak for arbitrary revolved grooves and true blends/fillets; it is not
      an ordered SolidWorks feature history.

### Third-batch implementation priority

1. Prototype **HPNet/ParSeNet-style primitive segmentation** or their geometric
   descriptors as proposal generators; do not replace the current full
   pipeline with either network.
2. Add **local residual agreement + edge/circle evidence**, informed by
   PIE-Net and topology-aware reconstruction. This is likely higher ROI than
   integrating LDIF or Neural-Pull.
3. Use **ExtrudeNet** for sketch/extrude decomposition ideas and **ComplexGen**
   for analytic surface/topology completion, especially spheres and tori.
4. Implement deterministic symmetry/pattern grouping before considering
   SymmetryNet; do not use JoinABLe for this task.
5. Keep the previously identified native SolidWorks frame/rollback fixes
   independent of these research integrations.

## Duplicates in the 2026-09-13 candidate list

These suggestions were useful, but they are not fresh papers:

- CADENA — already **FULL_TEXT_REVIEWED**
- CADReasoner — already **FULL_TEXT_REVIEWED**
- cadrille — already **FULL_TEXT_REVIEWED**; supplied year differs
- SkexGen — already **FULL_TEXT_REVIEWED**

## Current failure cases driving the next paper search (2026-09-13)

These are the live examples we just diagnosed. Future papers should help
**these** failures first, not generic CAD generation.

### Case A — Spool (`4da7faf2…`) · recognition failure
- Result: one native revolve, ~96.6% volume IoU, **0 residual features accepted**.
- Visually obvious misses: circumferential outer grooves and radial through-holes
  in the wall.
- Root causes already confirmed in CAD-View:
  - Revolve wins early and then residual search only proposes axial bosses/cuts
    or annular **inner** revolve-cuts, not outer grooves.
  - Hole/groove triangles merge into large freeform patches; no radial-hole
    cylinder candidates survive surface analysis.
  - Global IoU is already high, so local hole/groove proposals lose to the
    fixed improvement gate.
- Research relevance: **high** — needs better segmentation, local objectives,
  partial-feature completion, and pattern/symmetry recovery.

### Case B — Palm attachment (`802d04c0…` / `f341…`) · mixed failure
- Result: recipe finds 2 residual bosses + 2 radial holes (~91% manifold IoU),
  but SolidWorks rejects **feature 3** (`CADView Radial Hole 1`).
- Root causes already confirmed:
  - Search scores a 3D cylinder boolean, then the exporter maps it to a
    Top-Plane circle + midplane cut whose native extrusion axis does not match
    the scored cylinder axis.
  - Domed bosses are approximated as prism extrusions because local revolved
    bosses / domes / fillets are not in the action vocabulary.
  - Failed SolidWorks features abort without rollback or native retessellation
    scoring.
- Research relevance: **partial** — broader local feature vocabulary and
  native-kernel-in-the-loop search help. The plane/origin/basis mapping and
  body-count checks are **engineering fixes**, not paper searches.

### Engineering fixes planned after the next paper round
Do **not** treat these as research targets; implement them in CAD-View code:
1. Store every feature as a complete 3D origin + orthonormal frame, not only a
   named plane + direction index.
2. Compile that frame consistently into SolidWorks sketch coordinates.
3. After each native feature, require one merged solid body and geometry
   agreement; rollback on failure.
4. Score the actual SolidWorks rebuild, not only the manifold approximation.
5. Raise residual-step budget / make it adaptive once local features exist.

## Highest-ROI research problems for the next paper search

Prefer papers that address these first. They give the largest accuracy gain on
the spool/palm failures. Skip papers that only redo CADENA/CADReasoner-style
execute–measure–continue loops unless they add something below.

### Priority 1 — biggest immediate ROI
1. **Primitive-aware segmentation of intersecting CAD surfaces**
   - Want: methods that separate cylinders, tori/groove bands, planes, fillets,
     and hole interiors even when smooth adjacency merges them into one
     freeform patch.
   - Fixes: spool radial holes and circumferential grooves being invisible to
     residual search.
   - Useful keywords: RANSAC/primitive fitting, curvature-guided segmentation,
     CAD face clustering, intersecting cylinder detection, B-Rep patch typing.

2. **Local / topology-sensitive reconstruction objectives**
   - Want: losses or acceptance gates that preserve shallow grooves, small
     bores, and thin walls without requiring the correct CSG tree first.
     Global volume IoU must not erase semantically important low-volume detail.
   - Fixes: spool residual loop stopping at ~96.6% with 0 accepted features.
   - Useful keywords: local Chamfer / Hausdorff, normal-weighted deviation,
     thin-structure IoU, feature-aware residuals, topology preservation.

3. **Partial analytic-feature completion from incomplete residuals**
   - Want: recover a full cylinder/revolve/groove from clipped, fragmented, or
     sign-changing residual evidence rather than requiring one clean watertight
     residual component.
   - Fixes: spool holes/grooves that only appear as incomplete freeform scraps.
   - Useful keywords: incomplete cylinder fitting, feature completion, occluded
     bore recovery, residual-to-primitive association.

### Priority 2 — high ROI for both examples
4. **Symmetry, repetition, and native pattern recovery**
   - Want: detect repeated bosses/holes/grooves and emit one parameterized
     feature + circular/linear pattern rather than independent residuals.
   - Fixes: palm twin bosses/holes and any repeated spool wall holes.
   - Useful keywords: rotational symmetry detection, feature patterning,
     instance grouping, design-intent symmetry.

5. **Broader local feature vocabulary (domes, local revolves, fillets/blends)**
   - Want: local revolve bosses, hemispheres/domes, fillets, chamfers, and
     compound boss+hole features instead of convex-hull prism approximations.
   - Fixes: palm attachment domes approximated as extrudes; groove rounding on
     spool-like parts.
   - Useful keywords: local revolve recovery, fillet recognition, blend
     networks, analytic surface libraries beyond plane/cylinder.

### Priority 3 — important, but partly overlap earlier reviewed work
6. **Native-kernel-in-the-loop candidate validation**
   - Want: execute each candidate in OpenCascade/SolidWorks/Parasolid, reject
     rebuild failures transactionally, retessellate, and feed native error into
     search. Must handle competing partial trees, not only finished scripts.
   - Fixes: palm feature-3 SolidWorks rejection and disconnected bodies.
   - Note: ComAct / RLCAD already reviewed for adjacent pieces. Prefer papers
     with **prefix-level rollback + retessellation scoring**, not another COM
     demo alone.

7. **Long-horizon mixed-operation reconstruction with backtracking**
   - Want: ordered boss/cut extrude + revolve + groove + hole + fillet trees
     with real top-k / deletion / reordering beyond a 4-step residual budget.
   - Fixes: palm step-budget exhaustion and multi-feature spool histories.
   - Note: CADENA/CADReasoner already cover the generic iterative loop. Prefer
     papers with broader grammars + genuine beam/backtracking.

### Lower priority for this round
8. Design-intent / feature-order recovery from final geometry — useful later,
   but not the main blocker on the current spool/palm screenshots.
9. Noisy/non-watertight mesh repair — both current demos are already scaled
   watertight uploads.
10. Topology-stable persistent naming — needed for editable SolidWorks trees
    after success; secondary until recognition + native compile succeed.

## How to use this section when searching
- Bring papers aimed at **Priority 1–2** first.
- Exclude already **FULL_TEXT_REVIEWED** titles in this ledger.
- If a paper only says “iterative residual CAD with IoU reward,” mark it as
  likely redundant with CADENA/CADReasoner/cadrille unless it adds local
  objectives, primitive segmentation, patterns, or native-kernel validation.

## Procedure for future literature searches

1. Search this ledger by normalized title, DOI, and arXiv identifier before
   adding a candidate.
2. Report duplicates separately; do not count them toward a requested number
   of fresh papers.
3. Add newly discovered citations as **QUEUED_UNVERIFIED**.
4. Verify title, authors, year, venue, DOI/arXiv ID, PDF accessibility, and code
   repository before summarizing technical claims.
5. Change a status to **FULL_TEXT_REVIEWED** only after reading the actual PDF.
6. Record which CAD-View limitation the paper addresses and what implementation
   decision, if any, resulted from it.
7. Preserve rejected or inaccessible entries with a reason so they are not
   repeatedly rediscovered.
