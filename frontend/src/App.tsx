import { type ChangeEvent, useEffect, useState } from 'react'
import './App.css'
import {
  type LengthUnit,
  type MeshRecord,
  type PrimitiveAnalysis,
  type PrimitiveFitReport,
  type ParametricRecipeReport,
  type ReconstructionCapabilities,
  type ReconstructionEngineChoice,
  type ReconstructionJob,
  type SolidWorksExportRecord,
  type StepExportRecord,
  type Vec3,
  addCheckConstraint,
  analyzeParametricRecipe,
  analyzePrimitives,
  createPhotoReconstruction,
  createVideoReconstruction,
  declareMeshUnits,
  getMesh,
  getReconstructionCapabilities,
  getReconstructionJob,
  exportPrimitiveStep,
  exportMeshShapeStep,
  exportSolidWorksPart,
  listExports,
  listMeshes,
  repairMesh,
  scaleMesh,
  uploadMesh,
} from './api'
import { MeshViewer } from './MeshViewer'
import { PhotoMaskEditor } from './PhotoMaskEditor'

function App() {
  const [record, setRecord] = useState<MeshRecord | null>(null)
  const [observedRecord, setObservedRecord] = useState<MeshRecord | null>(null)
  const [uploading, setUploading] = useState(false)
  const [scaling, setScaling] = useState(false)
  const [declaringUnits, setDeclaringUnits] = useState(false)
  const [repairing, setRepairing] = useState(false)
  const [fillSmallHoles, setFillSmallHoles] = useState(false)
  const [repairMode, setRepairMode] = useState<
    'conservative' | 'watertight_proxy'
  >('conservative')
  const [wrapResolution, setWrapResolution] = useState(160)
  const [closingRadius, setClosingRadius] = useState(2)
  const [error, setError] = useState<string | null>(null)
  const [selectedPoints, setSelectedPoints] = useState<Vec3[]>([])
  const [selectionEnabled, setSelectionEnabled] = useState(false)
  const [selectionContext, setSelectionContext] = useState<
    'scale' | 'check' | null
  >(null)
  const [targetDistance, setTargetDistance] = useState('')
  const [unit, setUnit] = useState<LengthUnit>('mm')
  const [checkLabel, setCheckLabel] = useState('')
  const [checkDistance, setCheckDistance] = useState('')
  const [checkTolerance, setCheckTolerance] = useState('')
  const [checking, setChecking] = useState(false)
  const [capabilities, setCapabilities] =
    useState<ReconstructionCapabilities | null>(null)
  const [reconstructionEngine, setReconstructionEngine] =
    useState<ReconstructionEngineChoice>('auto')
  const [reconstructionJob, setReconstructionJob] =
    useState<ReconstructionJob | null>(null)
  const [primitiveAnalysis, setPrimitiveAnalysis] =
    useState<PrimitiveAnalysis | null>(null)
  const [stepExport, setStepExport] = useState<StepExportRecord | null>(null)
  const [parametricRecipe, setParametricRecipe] =
    useState<ParametricRecipeReport | null>(null)
  const [solidWorksExport, setSolidWorksExport] =
    useState<SolidWorksExportRecord | null>(null)
  const [analyzingPrimitives, setAnalyzingPrimitives] = useState(false)
  const [analyzingParametric, setAnalyzingParametric] = useState(false)
  const [exportingSolidWorks, setExportingSolidWorks] = useState(false)
  const [exportingStep, setExportingStep] = useState(false)
  const [fitThresholdPercent, setFitThresholdPercent] = useState('2')
  const [photoFiles, setPhotoFiles] = useState<File[] | null>(null)
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [recentMeshes, setRecentMeshes] = useState<MeshRecord[]>([])
  const [recentExports, setRecentExports] = useState<StepExportRecord[]>([])
  const [loadingLibrary, setLoadingLibrary] = useState(false)
  const [openingMeshId, setOpeningMeshId] = useState<string | null>(null)
  const reconstructionJobId = reconstructionJob?.id
  const reconstructionJobStatus = reconstructionJob?.status

  useEffect(() => {
    let cancelled = false
    const loadCapabilities = async () => {
      // Backend may still be starting when Vite opens; retry briefly.
      for (let attempt = 0; attempt < 8; attempt += 1) {
        try {
          const next = await getReconstructionCapabilities()
          if (!cancelled) setCapabilities(next)
          return
        } catch {
          await new Promise((resolve) => window.setTimeout(resolve, 500))
        }
      }
      if (!cancelled) setCapabilities(null)
    }
    void loadCapabilities()
    return () => {
      cancelled = true
    }
  }, [])

  // Restore only in-flight reconstructions after refresh. Finished jobs must not
  // force the previous mesh back into the workspace.
  useEffect(() => {
    const savedId = window.localStorage.getItem('cad-view-reconstruction-job')
    if (!savedId || reconstructionJob) return
    let cancelled = false
    void getReconstructionJob(savedId)
      .then((latest) => {
        if (cancelled) return
        if (latest.status === 'succeeded' || latest.status === 'failed') {
          window.localStorage.removeItem('cad-view-reconstruction-job')
          return
        }
        setReconstructionJob(latest)
      })
      .catch(() => {
        window.localStorage.removeItem('cad-view-reconstruction-job')
      })
    return () => {
      cancelled = true
    }
  }, [reconstructionJob])

  useEffect(() => {
    if (!reconstructionJob?.id) return
    if (
      reconstructionJob.status === 'succeeded' ||
      reconstructionJob.status === 'failed'
    ) {
      window.localStorage.removeItem('cad-view-reconstruction-job')
      return
    }
    window.localStorage.setItem(
      'cad-view-reconstruction-job',
      reconstructionJob.id,
    )
  }, [reconstructionJob?.id, reconstructionJob?.status])

  useEffect(() => {
    if (parametricRecipe && parametricRecipe.mesh_id !== record?.id) {
      setParametricRecipe(null)
      setSolidWorksExport(null)
    }
  }, [record?.id, parametricRecipe])

  useEffect(() => {
    if (
      !reconstructionJobId ||
      reconstructionJobStatus === 'succeeded' ||
      reconstructionJobStatus === 'failed'
    ) {
      return
    }

    let cancelled = false
    const poll = async () => {
      try {
        const latest = await getReconstructionJob(reconstructionJobId)
        if (cancelled) return

        if (latest.status === 'succeeded' && latest.output_mesh_id) {
          // Load the mesh before flipping job status to succeeded.
          // Updating status first unmounts this effect and used to cancel setRecord.
          const reconstructed = await getMesh(latest.output_mesh_id)
          if (cancelled) return
          setRecord(reconstructed)
          setObservedRecord(reconstructed)
          resetScaleInput()
          setReconstructionJob(latest)
        } else if (latest.status === 'failed') {
          setReconstructionJob(latest)
          setError(latest.error ?? 'Photogrammetry reconstruction failed.')
        } else {
          setReconstructionJob(latest)
        }
      } catch (pollError) {
        if (!cancelled) {
          setError(
            pollError instanceof Error
              ? pollError.message
              : 'Could not read reconstruction status.',
          )
        }
      }
    }

    const timer = window.setInterval(poll, 2000)
    void poll()
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [reconstructionJobId, reconstructionJobStatus])

  // Recover a finished job whose mesh never landed in UI state (Strict Mode / reload).
  useEffect(() => {
    if (
      reconstructionJob?.status !== 'succeeded' ||
      !reconstructionJob.output_mesh_id ||
      record?.id === reconstructionJob.output_mesh_id
    ) {
      return
    }

    let cancelled = false
    void getMesh(reconstructionJob.output_mesh_id)
      .then((reconstructed) => {
        if (cancelled) return
        setRecord(reconstructed)
        setObservedRecord(reconstructed)
        resetScaleInput()
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Could not load reconstructed mesh.',
          )
        }
      })

    return () => {
      cancelled = true
    }
  }, [
    reconstructionJob?.status,
    reconstructionJob?.output_mesh_id,
    record?.id,
  ])

  useEffect(() => {
    setPrimitiveAnalysis(null)
    setStepExport(null)
  }, [record?.id])

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return

    setUploading(true)
    setError(null)
    try {
      const uploaded = await uploadMesh(file)
      setRecord(uploaded)
      setObservedRecord(uploaded)
      resetScaleInput()
    } catch (uploadError) {
      setRecord(null)
      setObservedRecord(null)
      setError(
        uploadError instanceof Error ? uploadError.message : 'Mesh upload failed.',
      )
    } finally {
      setUploading(false)
      event.target.value = ''
    }
  }

  async function openLibrary() {
    setLibraryOpen(true)
    setLoadingLibrary(true)
    setError(null)
    try {
      const [meshes, exports] = await Promise.all([listMeshes(), listExports()])
      setRecentMeshes(meshes)
      setRecentExports(exports)
    } catch (libraryError) {
      setError(
        libraryError instanceof Error
          ? libraryError.message
          : 'Could not load saved meshes.',
      )
    } finally {
      setLoadingLibrary(false)
    }
  }

  async function openSavedMesh(meshId: string) {
    setOpeningMeshId(meshId)
    setError(null)
    try {
      const loaded = await getMesh(meshId)
      setRecord(loaded)
      setObservedRecord(loaded)
      resetScaleInput()
      setLibraryOpen(false)
      setPhotoFiles(null)
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Could not open saved mesh.',
      )
    } finally {
      setOpeningMeshId(null)
    }
  }

  function handlePhotos(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files ?? [])
    if (!selected.length) return
    setError(null)
    const minimum = capabilities?.minimum_image_count ?? 6
    if (selected.length < minimum) {
      setError(`Select at least ${minimum} overlapping photographs.`)
      event.target.value = ''
      return
    }
    // Clone before clearing the input so blob URLs stay valid in Chromium.
    const files = selected.map(
      (file) =>
        new File([file], file.name, {
          type: file.type || 'image/jpeg',
          lastModified: file.lastModified,
        }),
    )
    clearObservedSession()
    setPhotoFiles(files)
    event.target.value = ''
  }

  async function startMaskedPhotoReconstruction(masks: Blob[]) {
    if (!photoFiles) return
    setError(null)
    try {
      setReconstructionJob(
        await createPhotoReconstruction(
          photoFiles,
          masks,
          reconstructionEngine,
        ),
      )
      setPhotoFiles(null)
    } catch (reconstructionError) {
      setError(
        reconstructionError instanceof Error
          ? reconstructionError.message
          : 'Could not start photo reconstruction.',
      )
      throw reconstructionError
    }
  }

  async function handleVideo(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setError(null)
    try {
      clearObservedSession()
      setReconstructionJob(
        await createVideoReconstruction(file, reconstructionEngine),
      )
    } catch (reconstructionError) {
      setError(
        reconstructionError instanceof Error
          ? reconstructionError.message
          : 'Could not start video reconstruction.',
      )
    } finally {
      event.target.value = ''
    }
  }

  function resetScaleInput() {
    setSelectedPoints([])
    setSelectionEnabled(false)
    setSelectionContext(null)
    setTargetDistance('')
  }

  function clearObservedSession() {
    window.localStorage.removeItem('cad-view-reconstruction-job')
    setReconstructionJob(null)
    setPhotoFiles(null)
    setRecord(null)
    setObservedRecord(null)
    setPrimitiveAnalysis(null)
    setStepExport(null)
    setParametricRecipe(null)
    setSolidWorksExport(null)
    resetScaleInput()
    setError(null)
  }

  function beginPointSelection(context: 'scale' | 'check') {
    setSelectedPoints([])
    setSelectionContext(context)
    setSelectionEnabled(true)
    setError(null)
  }

  function handlePointPick(point: Vec3) {
    setSelectedPoints((current) => {
      const next = [...current, point].slice(0, 2)
      if (next.length === 2) setSelectionEnabled(false)
      return next
    })
  }

  async function applyDeclareUnits() {
    if (!record) return
    setDeclaringUnits(true)
    setError(null)
    try {
      const declared = await declareMeshUnits(record.id, unit)
      setRecord(declared)
      setObservedRecord(declared)
      setPrimitiveAnalysis(null)
      setStepExport(null)
    } catch (declareError) {
      setError(
        declareError instanceof Error
          ? declareError.message
          : 'Could not declare working units.',
      )
    } finally {
      setDeclaringUnits(false)
    }
  }

  async function applyScale() {
    if (
      !record ||
      selectionContext !== 'scale' ||
      selectedPoints.length !== 2
    ) {
      return
    }
    const parsedDistance = Number(targetDistance)
    if (!Number.isFinite(parsedDistance) || parsedDistance <= 0) {
      setError('Enter a positive known distance.')
      return
    }

    setScaling(true)
    setError(null)
    try {
      const scaled = await scaleMesh(record.id, {
        point_a: selectedPoints[0],
        point_b: selectedPoints[1],
        target_distance: parsedDistance,
        unit,
      })
      setRecord(scaled)
      resetScaleInput()
    } catch (scaleError) {
      setError(
        scaleError instanceof Error ? scaleError.message : 'Scaling failed.',
      )
    } finally {
      setScaling(false)
    }
  }

  async function applyRepair() {
    if (!record) return
    setRepairing(true)
    setError(null)
    try {
      const repaired = await repairMesh(record.id, {
        fill_small_holes: fillSmallHoles,
        mode: repairMode,
        voxel_resolution: wrapResolution,
        closing_radius_voxels: closingRadius,
        smoothing_iterations: 6,
      })
      setRecord(repaired)
      resetScaleInput()
    } catch (repairError) {
      setError(
        repairError instanceof Error ? repairError.message : 'Repair failed.',
      )
    } finally {
      setRepairing(false)
    }
  }

  async function applyCheck() {
    if (!record || selectedPoints.length !== 2) return
    const expectedDistance = Number(checkDistance)
    const tolerance = Number(checkTolerance)
    if (!checkLabel.trim()) {
      setError('Name the check dimension.')
      return
    }
    if (!Number.isFinite(expectedDistance) || expectedDistance <= 0) {
      setError('Enter a positive expected distance.')
      return
    }
    if (!Number.isFinite(tolerance) || tolerance < 0) {
      setError('Enter a non-negative tolerance.')
      return
    }

    setChecking(true)
    setError(null)
    try {
      const checked = await addCheckConstraint(record.id, {
        label: checkLabel.trim(),
        point_a: selectedPoints[0],
        point_b: selectedPoints[1],
        expected_distance: expectedDistance,
        tolerance,
      })
      setRecord(checked)
      setSelectedPoints([])
      setSelectionEnabled(false)
      setSelectionContext(null)
      setCheckLabel('')
      setCheckDistance('')
      setCheckTolerance('')
    } catch (checkError) {
      setError(
        checkError instanceof Error
          ? checkError.message
          : 'Dimensional check failed.',
      )
    } finally {
      setChecking(false)
    }
  }

  async function runPrimitiveAnalysis() {
    if (!record) return
    setAnalyzingPrimitives(true)
    setError(null)
    try {
      setPrimitiveAnalysis(await analyzePrimitives(record.id))
    } catch (analysisError) {
      setError(
        analysisError instanceof Error
          ? analysisError.message
          : 'Primitive analysis failed.',
      )
    } finally {
      setAnalyzingPrimitives(false)
    }
  }

  async function runParametricAnalysis() {
    if (!record) return
    setAnalyzingParametric(true)
    setError(null)
    setSolidWorksExport(null)
    try {
      setParametricRecipe(await analyzeParametricRecipe(record.id))
    } catch (analysisError) {
      setError(
        analysisError instanceof Error
          ? analysisError.message
          : 'Parametric feature analysis failed.',
      )
    } finally {
      setAnalyzingParametric(false)
    }
  }

  async function createSolidWorksExport() {
    if (!record) return
    setExportingSolidWorks(true)
    setError(null)
    try {
      setSolidWorksExport(await exportSolidWorksPart(record.id, true))
    } catch (exportError) {
      setError(
        exportError instanceof Error
          ? exportError.message
          : 'SolidWorks feature-tree export failed.',
      )
    } finally {
      setExportingSolidWorks(false)
    }
  }

  async function createMeshShapeStepExport() {
    if (!record) return
    setExportingStep(true)
    setError(null)
    try {
      setStepExport(await exportMeshShapeStep(record.id))
    } catch (exportError) {
      setError(
        exportError instanceof Error
          ? exportError.message
          : 'Mesh STEP export failed.',
      )
    } finally {
      setExportingStep(false)
    }
  }

  async function createStepExport(
    primitiveType: 'box' | 'cylinder',
  ) {
    if (!record) return
    const threshold = Number(fitThresholdPercent) / 100
    if (!Number.isFinite(threshold) || threshold <= 0 || threshold > 0.25) {
      setError('STEP fit threshold must be greater than 0% and at most 25%.')
      return
    }

    setExportingStep(true)
    setError(null)
    try {
      setStepExport(
        await exportPrimitiveStep(record.id, primitiveType, threshold),
      )
    } catch (exportError) {
      setError(
        exportError instanceof Error ? exportError.message : 'STEP export failed.',
      )
    } finally {
      setExportingStep(false)
    }
  }

  const quality = record?.qualification
  const pickedDistance =
    selectedPoints.length === 2
      ? distanceBetween(selectedPoints[0], selectedPoints[1])
      : null
  const linearUnit = record?.unit ?? 'source units'

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">CAD-VIEW / OBSERVED GEOMETRY</span>
          <h1>Mesh qualification workspace</h1>
        </div>
        <div className="source-state">
          <span className="status-dot" />
          {record ? 'Immutable source captured' : 'Awaiting source'}
        </div>
      </header>

      <section className="workspace">
        <div className="viewport-panel">
          {record ? (
            <>
              <MeshViewer
                extension={record.extension}
                url={record.download_url}
                extents={record.qualification.extents}
                selectedPoints={selectedPoints}
                selectionEnabled={selectionEnabled}
                onPointPick={handlePointPick}
              />
              <div className="viewport-label">
                <span>
                  {artifactLabel(record)}
                </span>
                <strong>{record.provenance.original_filename}</strong>
              </div>
            </>
          ) : photoFiles ? (
            <PhotoMaskEditor
              files={photoFiles}
              samAvailable={capabilities?.segmentation_available ?? false}
              onCancel={() => setPhotoFiles(null)}
              onSubmit={startMaskedPhotoReconstruction}
              onError={setError}
            />
          ) : (
            <div className="upload-drop">
              <span className="upload-mark">+</span>
              <strong>
                {reconstructionJob &&
                !['succeeded', 'failed'].includes(reconstructionJob.status)
                  ? `Reconstruction: ${reconstructionJob.stage.replaceAll('_', ' ')}`
                  : reconstructionJob?.status === 'succeeded' &&
                      reconstructionJob.output_mesh_id
                    ? 'Reconstruction complete'
                    : 'Create or load observed geometry'}
              </strong>
              <small>
                Mesh uploads are the main CAD path: declare units → fit box/
                cylinder → export STEP. Photo/video reconstruction is
                experimental and optional.
              </small>
              {reconstructionJob?.status === 'succeeded' &&
                reconstructionJob.output_mesh_id && (
                  <button
                    type="button"
                    className="control-button primary"
                    onClick={() => {
                      void getMesh(reconstructionJob.output_mesh_id!)
                        .then((reconstructed) => {
                          setRecord(reconstructed)
                          setObservedRecord(reconstructed)
                          resetScaleInput()
                        })
                        .catch((loadError) => {
                          setError(
                            loadError instanceof Error
                              ? loadError.message
                              : 'Could not load reconstructed mesh.',
                          )
                        })
                    }}
                  >
                    Open reconstructed mesh
                  </button>
                )}
              {(record || reconstructionJob) && (
                <button
                  type="button"
                  className="control-button"
                  onClick={() => clearObservedSession()}
                  disabled={
                    !!reconstructionJob &&
                    !['succeeded', 'failed'].includes(reconstructionJob.status)
                  }
                >
                  Clear result / new capture
                </button>
              )}
              <div className="engine-picker">
                <label htmlFor="reconstruction-engine">Engine</label>
                <select
                  id="reconstruction-engine"
                  value={reconstructionEngine}
                  onChange={(event) =>
                    setReconstructionEngine(
                      event.target.value as ReconstructionEngineChoice,
                    )
                  }
                  disabled={
                    !!reconstructionJob &&
                    !['succeeded', 'failed'].includes(reconstructionJob.status)
                  }
                >
                  <option value="auto">
                    Auto (Meshroom full-frame SfM → VGGT rescue)
                  </option>
                  <option
                    value="vggt"
                    disabled={capabilities?.neural_available === false}
                  >
                    VGGT neural (low-texture / black objects)
                  </option>
                  <option
                    value="triposr"
                    disabled={capabilities?.generative_available === false}
                  >
                    TripoSR scaffold (complete shape, inferred geometry)
                  </option>
                  <option
                    value="meshroom"
                    disabled={
                      !(
                        capabilities?.meshroom_available ??
                        capabilities?.available
                      )
                    }
                  >
                    Meshroom (full-frame pose, masked dense; VGGT rescue)
                  </option>
                </select>
              </div>
              <div className="ingestion-actions">
                <button
                  type="button"
                  className="control-button"
                  onClick={() => void openLibrary()}
                  disabled={
                    !!reconstructionJob &&
                    !['succeeded', 'failed'].includes(reconstructionJob.status)
                  }
                >
                  Open a mesh / CAD
                </button>
                <label>
                  Upload mesh
                  <input
                    type="file"
                    accept=".stl,.obj,.ply"
                    onChange={handleFile}
                    disabled={uploading}
                  />
                </label>
                <label
                  className={capabilities?.supports_photos ? '' : 'disabled'}
                  title={
                    capabilities?.supports_photos
                      ? 'Upload overlapping photographs'
                      : 'Meshroom installation is not available yet'
                  }
                >
                  Upload photos
                  <input
                    type="file"
                    accept=".jpg,.jpeg,.png,.tif,.tiff"
                    multiple
                    onChange={handlePhotos}
                    disabled={!capabilities?.supports_photos}
                  />
                </label>
                <label
                  className={capabilities?.supports_video ? '' : 'disabled'}
                  title={
                    capabilities?.supports_video
                      ? 'Upload a capture video'
                      : 'Meshroom installation is not available yet'
                  }
                >
                  Upload video
                  <input
                    type="file"
                    accept=".mp4,.mov,.avi,.mkv,.webm"
                    onChange={handleVideo}
                    disabled={!capabilities?.supports_video}
                  />
                </label>
              </div>
              <small>
                {capabilities?.available
                  ? [
                      capabilities.neural_available
                        ? 'VGGT neural ready'
                        : null,
                      capabilities.meshroom_available ||
                      Boolean(capabilities.executable)
                        ? 'Meshroom ready'
                        : null,
                      `min ${capabilities.minimum_image_count}, recommend 20–40 overlapping stills`,
                    ]
                      .filter(Boolean)
                      .join(' · ')
                  : 'Local reconstruction engine unavailable'}
                {reconstructionJob?.resolved_engine && (
                  <> · using {reconstructionJob.resolved_engine}</>
                )}
              </small>
              {reconstructionEngine === 'triposr' && (
                <p className="review-warning">
                  TripoSR uses the best masked photo to generate a plausible
                  complete object. Hidden surfaces and dimensions are inferred,
                  not measured. Use it as a scaffold and validate every CAD
                  dimension independently.
                </p>
              )}
              {error && <p className="upload-error">{error}</p>}
            </div>
          )}
        </div>

        <aside className="inspector">
          <section>
            <div className="section-heading">
              <span>01</span>
              <h2>Provenance</h2>
            </div>
            {record ? (
              <dl className="data-list">
                <div>
                  <dt>State</dt>
                  <dd className="state-value">
                    {geometryStateLabel(record)}
                  </dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>{sourceKindLabel(record)}</dd>
                </div>
                <div>
                  <dt>SHA-256</dt>
                  <dd className="mono">{record.provenance.sha256.slice(0, 12)}…</dd>
                </div>
                <div>
                  <dt>Processing</dt>
                  <dd>
                    {record.provenance.processing_steps.length
                      ? record.provenance.processing_steps.join(', ')
                      : 'None'}
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="muted">Source history appears after ingestion.</p>
            )}
          </section>

          <section>
            <div className="section-heading">
              <span>02</span>
              <h2>Topology</h2>
            </div>
            {quality ? (
              <div className="metric-grid">
                <Metric label="Vertices" value={quality.vertex_count.toLocaleString()} />
                <Metric label="Faces" value={quality.face_count.toLocaleString()} />
                <Metric label="Components" value={quality.connected_components} />
                <Metric
                  label="Watertight"
                  value={quality.is_watertight ? 'Pass' : 'Fail'}
                  status={quality.is_watertight}
                />
                <Metric
                  label="Winding"
                  value={quality.is_winding_consistent ? 'Pass' : 'Fail'}
                  status={quality.is_winding_consistent}
                />
                <Metric label="Euler no." value={quality.euler_number} />
              </div>
            ) : (
              <p className="muted">No geometry has been qualified.</p>
            )}
          </section>

          <section>
            <div className="section-heading">
              <span>03</span>
              <h2>Units &amp; scale</h2>
            </div>
            {record ? (
              <div className="scale-controls">
                <p className="muted">
                  For mesh→CAD, declare working units first (geometry unchanged).
                  Physical two-point scale remains optional.
                </p>

                {record.unit ? (
                  <div className="scale-result">
                    <strong>Working units: {record.unit}</strong>
                    <span>
                      {record.scale_application
                        ? `Metrology-scaled × ${formatNumber(record.scale_application.scale_factor)}`
                        : record.provenance.processing_steps.includes(
                              'declare_units',
                            )
                          ? 'Assumed source units (not metrology-scaled)'
                          : 'Units assigned'}
                    </span>
                  </div>
                ) : (
                  <div className="distance-input">
                    <select
                      value={unit}
                      onChange={(event) =>
                        setUnit(event.target.value as LengthUnit)
                      }
                      aria-label="Working length unit"
                    >
                      <option value="mm">mm</option>
                      <option value="cm">cm</option>
                      <option value="m">m</option>
                      <option value="in">in</option>
                    </select>
                    <button
                      type="button"
                      className="control-button primary"
                      onClick={() => void applyDeclareUnits()}
                      disabled={declaringUnits}
                    >
                      {declaringUnits
                        ? 'Assigning units…'
                        : 'Use these units for CAD'}
                    </button>
                  </div>
                )}

                {record.scale_application ? (
                  <div className="scale-result">
                    <strong>
                      {formatNumber(record.scale_application.target_distance)}{' '}
                      {record.scale_application.unit}
                    </strong>
                    <span>
                      Uniform factor{' '}
                      {formatNumber(record.scale_application.scale_factor)}
                    </span>
                    <span>
                      Residual{' '}
                      {formatNumber(record.scale_application.residual)}{' '}
                      {record.scale_application.unit}
                    </span>
                  </div>
                ) : (
                  <p className="muted">
                    Optional: select two surface points and enter their known
                    physical distance.
                  </p>
                )}

                <button
                  type="button"
                  className={
                    selectionEnabled && selectionContext === 'scale'
                      ? 'control-button active'
                      : 'control-button'
                  }
                  onClick={() => beginPointSelection('scale')}
                >
                  {selectionEnabled && selectionContext === 'scale'
                    ? `Pick point ${selectedPoints.length === 0 ? 'A' : 'B'}`
                    : 'Select anchor points'}
                </button>

                {selectionContext === 'scale' && selectedPoints.length > 0 && (
                  <div className="point-readout">
                    {selectedPoints.map((point, index) => (
                      <span key={index}>
                        {index === 0 ? 'A' : 'B'} · {formatPoint(point)}
                      </span>
                    ))}
                    {pickedDistance !== null && (
                      <strong>
                        Mesh distance: {formatNumber(pickedDistance)} source units
                      </strong>
                    )}
                  </div>
                )}

                <div className="distance-input">
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={targetDistance}
                    onChange={(event) => setTargetDistance(event.target.value)}
                    placeholder="Known distance"
                    aria-label="Known physical distance"
                  />
                  <select
                    value={unit}
                    onChange={(event) => setUnit(event.target.value as LengthUnit)}
                    aria-label="Distance unit"
                  >
                    <option value="mm">mm</option>
                    <option value="cm">cm</option>
                    <option value="m">m</option>
                    <option value="in">in</option>
                  </select>
                </div>

                <button
                  type="button"
                  className="control-button primary"
                  disabled={
                    selectionContext !== 'scale' ||
                    selectedPoints.length !== 2 ||
                    !targetDistance ||
                    scaling
                  }
                  onClick={applyScale}
                >
                  {scaling ? 'Creating derivative…' : 'Create scaled derivative'}
                </button>

                {record.provenance.geometry_state === 'scaled' &&
                  observedRecord && (
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => {
                        setRecord(observedRecord)
                        resetScaleInput()
                      }}
                    >
                      Return to observed source
                    </button>
                  )}
              </div>
            ) : (
              <p className="muted">Load geometry before adding units or scale.</p>
            )}
          </section>

          <section>
            <div className="section-heading">
              <span>04</span>
              <h2>Envelope</h2>
            </div>
            {quality ? (
              <dl className="data-list">
                {quality.extents.map((extent, index) => (
                  <div key={['X', 'Y', 'Z'][index]}>
                    <dt>{['X', 'Y', 'Z'][index]} extent</dt>
                    <dd>{formatNumber(extent)} {linearUnit}</dd>
                  </div>
                ))}
                <div>
                  <dt>Volume</dt>
                  <dd>
                    {quality.volume === null
                      ? 'Unavailable'
                      : `${formatNumber(Math.abs(quality.volume))} ${
                          record?.unit ? `${record.unit}³` : 'source units³'
                        }`}
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="muted">Dimensions require a valid mesh.</p>
            )}
          </section>

          <section>
            <div className="section-heading">
              <span>05</span>
              <h2>Conservative repair</h2>
            </div>
            {record ? (
              <div className="scale-controls">
                <p className="muted">
                  The observed scan stays immutable. Choose topology-only cleanup
                  or create a separate inferred watertight proxy.
                </p>
                <label className="repair-option">
                  <input
                    type="radio"
                    name="repair-mode"
                    checked={repairMode === 'conservative'}
                    onChange={() => setRepairMode('conservative')}
                  />
                  <span>
                    Conservative topology cleanup
                    <small>Fix winding and duplicates without moving vertices.</small>
                  </span>
                </label>
                <label className="repair-option">
                  <input
                    type="radio"
                    name="repair-mode"
                    checked={repairMode === 'watertight_proxy'}
                    onChange={() => setRepairMode('watertight_proxy')}
                  />
                  <span>
                    Watertight scan proxy
                    <small>
                      Voxel-wrap, close narrow defects, and smooth for printing or
                      CAD analysis. This infers geometry.
                    </small>
                  </span>
                </label>
                {repairMode === 'conservative' ? (
                  <label className="repair-option">
                    <input
                      type="checkbox"
                      checked={fillSmallHoles}
                      onChange={(event) => setFillSmallHoles(event.target.checked)}
                    />
                    <span>
                      Fill simple boundary loops
                      <small>
                        Handles openings larger than triangles/quads; review every
                        inferred patch.
                      </small>
                    </span>
                  </label>
                ) : (
                  <div className="repair-settings">
                    <label>
                      <span>Wrap resolution</span>
                      <input
                        type="range"
                        min="96"
                        max="256"
                        step="16"
                        value={wrapResolution}
                        onChange={(event) =>
                          setWrapResolution(Number(event.target.value))
                        }
                      />
                      <strong>{wrapResolution}</strong>
                    </label>
                    <label>
                      <span>Defect closing</span>
                      <input
                        type="range"
                        min="0"
                        max="5"
                        step="1"
                        value={closingRadius}
                        onChange={(event) =>
                          setClosingRadius(Number(event.target.value))
                        }
                      />
                      <strong>{closingRadius} vox</strong>
                    </label>
                    <p className="review-warning">
                      Stronger closing removes more dents and tunnels, but can erase
                      intentional slots or holes.
                    </p>
                  </div>
                )}
                <button
                  type="button"
                  className="control-button"
                  onClick={applyRepair}
                  disabled={repairing}
                >
                  {repairing
                    ? 'Creating derived mesh…'
                    : repairMode === 'watertight_proxy'
                      ? 'Create watertight proxy'
                      : 'Repair topology'}
                </button>

                {record.repair_report && (
                  <div className="repair-report">
                    <div>
                      <span>Watertight</span>
                      <strong
                        className={
                          record.repair_report.after.is_watertight
                            ? 'metric-pass'
                            : 'metric-fail'
                        }
                      >
                        {record.repair_report.after.is_watertight ? 'Pass' : 'Fail'}
                      </strong>
                    </div>
                    <div>
                      <span>Duplicate faces removed</span>
                      <strong>{record.repair_report.duplicate_faces_removed}</strong>
                    </div>
                    <div>
                      <span>Faces added</span>
                      <strong>{record.repair_report.faces_added}</strong>
                    </div>
                    <div>
                      <span>Boundary loops filled</span>
                      <strong>
                        {record.repair_report.boundary_loops_filled}
                      </strong>
                    </div>
                    <div>
                      <span>
                        {record.repair_report.method === 'voxel_wrap'
                          ? 'Maximum proxy deviation'
                          : 'Existing vertex displacement'}
                      </span>
                      <strong>
                        {formatNumber(
                          record.repair_report.max_existing_vertex_displacement,
                        )}
                      </strong>
                    </div>
                    {record.repair_report.normalized_rms_percent !== null && (
                      <div>
                        <span>Symmetric RMS deviation</span>
                        <strong>
                          {formatNumber(
                            record.repair_report.normalized_rms_percent,
                          )}
                          %
                        </strong>
                      </div>
                    )}
                    {record.repair_report.requires_human_review && (
                      <p className="review-warning">
                        Review required: new closure faces were inferred.
                      </p>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <p className="muted">Load geometry before running repair.</p>
            )}
          </section>

          <section>
            <div className="section-heading">
              <span>06</span>
              <h2>Independent checks</h2>
            </div>
            {record?.unit ? (
              <div className="scale-controls">
                <p className="muted">
                  Check dimensions do not alter geometry. They test whether
                  independent measurements agree within tolerance.
                </p>
                <button
                  type="button"
                  className={
                    selectionEnabled && selectionContext === 'check'
                      ? 'control-button active'
                      : 'control-button'
                  }
                  onClick={() => beginPointSelection('check')}
                >
                  {selectionEnabled && selectionContext === 'check'
                    ? `Pick check point ${
                        selectedPoints.length === 0 ? 'A' : 'B'
                      }`
                    : 'Select check points'}
                </button>

                {selectionContext === 'check' && selectedPoints.length > 0 && (
                  <div className="point-readout">
                    {selectedPoints.map((point, index) => (
                      <span key={index}>
                        {index === 0 ? 'A' : 'B'} · {formatPoint(point)}
                      </span>
                    ))}
                    {pickedDistance !== null && (
                      <strong>
                        Measured: {formatNumber(pickedDistance)} {record.unit}
                      </strong>
                    )}
                  </div>
                )}

                <input
                  className="field-input"
                  value={checkLabel}
                  onChange={(event) => setCheckLabel(event.target.value)}
                  placeholder="Check name, e.g. overall height"
                  aria-label="Check dimension name"
                />
                <div className="check-inputs">
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={checkDistance}
                    onChange={(event) => setCheckDistance(event.target.value)}
                    placeholder={`Expected (${record.unit})`}
                    aria-label="Expected check distance"
                  />
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={checkTolerance}
                    onChange={(event) => setCheckTolerance(event.target.value)}
                    placeholder={`± tolerance`}
                    aria-label="Check tolerance"
                  />
                </div>
                <button
                  type="button"
                  className="control-button primary"
                  disabled={
                    selectionContext !== 'check' ||
                    selectedPoints.length !== 2 ||
                    !checkLabel.trim() ||
                    !checkDistance ||
                    !checkTolerance ||
                    checking
                  }
                  onClick={applyCheck}
                >
                  {checking ? 'Recording check…' : 'Record dimensional check'}
                </button>

                {record.check_constraints.length > 0 && (
                  <div className="check-results">
                    {record.check_constraints.map((check) => (
                      <div key={check.id}>
                        <span>
                          <strong>{check.label}</strong>
                          <small>
                            {formatNumber(check.measured_distance)} /{' '}
                            {formatNumber(check.expected_distance)} {check.unit}
                          </small>
                        </span>
                        <b className={check.passes ? 'metric-pass' : 'metric-fail'}>
                          {check.residual >= 0 ? '+' : ''}
                          {formatNumber(check.residual)}
                        </b>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="muted">
                Apply a physical scale before adding check dimensions.
              </p>
            )}
          </section>

          <section>
            <div className="section-heading">
              <span>07</span>
              <h2>Editable CAD reconstruction</h2>
            </div>
            {record?.unit ? (
              <div className="scale-controls">
                <p className="muted">
                  Multi-section slicing segments depth-varying regions, extracts
                  perimeter groove paths, and validates the recovered CAD
                  against the source mesh. SolidWorks builds native sketches
                  and features, not an imported dumb body.
                </p>
                <button
                  type="button"
                  className="control-button primary"
                  onClick={() => void runParametricAnalysis()}
                  disabled={analyzingParametric}
                >
                  {analyzingParametric
                    ? 'Recovering feature recipe…'
                    : 'Analyze editable feature tree'}
                </button>

                {parametricRecipe && (
                  <div className="primitive-results">
                    <div>
                      <span>
                        <strong>
                          {parametricRecipe.strategy ===
                          'residual_refined_reconstruction'
                            ? 'Residual-refined feature tree recovered'
                            : parametricRecipe.strategy ===
                              'revolve_reconstruction'
                            ? 'Native revolve recovered'
                            : parametricRecipe.strategy ===
                              'sweep_cut_reconstruction'
                            ? 'Native swept groove selected'
                            : parametricRecipe.diagnostics.groove_detected
                            ? 'Perimeter groove recovered'
                            : 'Prismatic base recovered'}
                        </strong>
                        <small>
                          {parametricRecipe.diagnostics.agreement?.method ===
                          'volume_iou'
                            ? 'Volume IoU '
                            : 'Confidence '}
                          {formatNumber(parametricRecipe.confidence * 100)}% ·{' '}
                          {parametricRecipe.features.length} native feature
                          {parametricRecipe.features.length === 1 ? '' : 's'}
                        </small>
                        {parametricRecipe.diagnostics.quality && (
                          <small>
                            Reconstruction quality:{' '}
                            {parametricRecipe.diagnostics.quality.status} ·
                            export{' '}
                            {parametricRecipe.diagnostics.quality
                              .export_recommended
                              ? 'enabled'
                              : 'blocked'}
                          </small>
                        )}
                        {parametricRecipe.features.map((feature) => (
                          <small key={feature.id}>
                            {feature.name} ·{' '}
                            {feature.type === 'revolve' ||
                            feature.type === 'revolve_cut'
                              ? `${formatNumber(
                                  feature.angle_degrees ?? 360,
                                )}° ${
                                  feature.type === 'revolve_cut'
                                    ? 'cut'
                                    : 'boss'
                                } about a sketch centerline`
                              : `${
                                  feature.type === 'sweep_cut'
                                    ? 'profile depth'
                                    : 'depth'
                                } ${formatNumber(feature.depth ?? 0)} ${
                                  parametricRecipe.unit
                                }`}
                            {feature.start_offset && feature.start_offset > 0
                              ? ` · starts at ${formatNumber(feature.start_offset)} ${parametricRecipe.unit}`
                              : ''}
                          </small>
                        ))}
                        {parametricRecipe.diagnostics.revolve_axis_index !=
                          null && (
                          <small>
                            Profile{' '}
                            {parametricRecipe.diagnostics.profile_point_count ??
                              0}{' '}
                            points · max radius{' '}
                            {formatNumber(
                              parametricRecipe.diagnostics.maximum_radius ?? 0,
                            )}{' '}
                            {parametricRecipe.unit}
                            {parametricRecipe.diagnostics.bore_radius
                              ? ` · bore radius ${formatNumber(
                                  parametricRecipe.diagnostics.bore_radius,
                                )} ${parametricRecipe.unit}`
                              : ''}{' '}
                            · out-of-round{' '}
                            {formatNumber(
                              (parametricRecipe.diagnostics.roundness_error ??
                                0) * 100,
                            )}
                            %
                          </small>
                        )}
                        {parametricRecipe.diagnostics.groove_detected && (
                          <small>
                            Groove width{' '}
                            {formatNumber(
                              parametricRecipe.diagnostics.groove_width ?? 0,
                            )}{' '}
                            {parametricRecipe.unit} · side flange{' '}
                            {formatNumber(
                              parametricRecipe.diagnostics.flange_depth ?? 0,
                            )}{' '}
                            {parametricRecipe.unit}
                          </small>
                        )}
                        {parametricRecipe.diagnostics.feature_intent
                          ?.orthogonal_section_analysis && (
                          <small>
                            Intent test:{' '}
                            {parametricRecipe.diagnostics.feature_intent
                              .orthogonal_section_analysis.decision ===
                            'ambiguous_equivalent'
                              ? 'geometrically ambiguous; conservative cut retained'
                              : parametricRecipe.diagnostics.feature_intent
                                    .selected === 'sweep_cut'
                              ? 'Sweep-Cut won'
                              : 'stacked cut retained'}{' '}
                            · sweep score{' '}
                            {formatNumber(
                              parametricRecipe.diagnostics.feature_intent
                                .orthogonal_section_analysis.hypotheses[0]
                                .score,
                            )}{' '}
                            vs stacked{' '}
                            {formatNumber(
                              parametricRecipe.diagnostics.feature_intent
                                .orthogonal_section_analysis.hypotheses[1]
                                .score,
                            )}{' '}
                            · profile variation{' '}
                            {formatNumber(
                              parametricRecipe.diagnostics.feature_intent
                                .orthogonal_section_analysis
                                .sweep_normalized_rms * 100,
                            )}
                            % · path coverage{' '}
                            {formatNumber(
                              parametricRecipe.diagnostics.feature_intent
                                .orthogonal_section_analysis.coverage * 100,
                            )}
                            %
                          </small>
                        )}
                        {parametricRecipe.diagnostics.residual_refinement
                          ?.attempted && (
                          <small>
                            Residual loop:{' '}
                            {
                              parametricRecipe.diagnostics.residual_refinement
                                .accepted_features.length
                            }{' '}
                            feature
                            {parametricRecipe.diagnostics.residual_refinement
                              .accepted_features.length === 1
                              ? ''
                              : 's'}{' '}
                            accepted
                            {parametricRecipe.diagnostics.residual_refinement
                              .beam_width
                              ? ` · beam width ${parametricRecipe.diagnostics.residual_refinement.beam_width}`
                              : ''}{' '}
                            · stopped on{' '}
                            {parametricRecipe.diagnostics.residual_refinement.stop_reason?.replaceAll(
                              '_',
                              ' ',
                            )}
                          </small>
                        )}
                        {parametricRecipe.diagnostics.surface_analysis && (
                          <small>
                            Surface patches:{' '}
                            {
                              parametricRecipe.diagnostics.surface_analysis
                                .counts.plane
                            }{' '}
                            planar ·{' '}
                            {
                              parametricRecipe.diagnostics.surface_analysis
                                .counts.cylinder
                            }{' '}
                            cylindrical ·{' '}
                            {
                              parametricRecipe.diagnostics.surface_analysis
                                .counts.freeform
                            }{' '}
                            freeform ·{' '}
                            {
                              parametricRecipe.diagnostics.surface_analysis
                                .curvature_analysis.bands.length
                            }{' '}
                            high-curvature bands
                          </small>
                        )}
                        {parametricRecipe.diagnostics.hypothesis_search && (
                          <details className="hypothesis-ranking">
                            <summary>
                              Chose{' '}
                              {
                                parametricRecipe.diagnostics.hypothesis_search
                                  .selected.hypothesis
                              }{' '}
                              from{' '}
                              {
                                parametricRecipe.diagnostics.hypothesis_search
                                  .hypotheses.length
                              }{' '}
                              scored hypotheses
                            </summary>
                            <ul>
                              {parametricRecipe.diagnostics.hypothesis_search.hypotheses.map(
                                (hypothesis) => (
                                  <li
                                    key={`${hypothesis.hypothesis}-${hypothesis.axis_index}`}
                                    className={
                                      hypothesis.selected ? 'selected' : ''
                                    }
                                  >
                                    {hypothesis.hypothesis} · axis{' '}
                                    {hypothesis.axis_index} ·{' '}
                                    IoU{' '}
                                    {formatNumber(hypothesis.score * 100)}% ·
                                    local rank{' '}
                                    {formatNumber(
                                      hypothesis.selection_score * 100,
                                    )}
                                    %
                                  </li>
                                ),
                              )}
                            </ul>
                          </details>
                        )}
                        {parametricRecipe.diagnostics.deviation?.rms != null && (
                          <small>
                            Mesh → CAD deviation: RMS{' '}
                            {formatNumber(
                              parametricRecipe.diagnostics.deviation.rms,
                            )}{' '}
                            {parametricRecipe.unit} · 95% within{' '}
                            {formatNumber(
                              parametricRecipe.diagnostics.deviation.p95 ?? 0,
                            )}{' '}
                            {parametricRecipe.unit}
                          </small>
                        )}
                        {parametricRecipe.diagnostics.agreement
                          ?.surface_agreement.normal_alignment != null && (
                          <small>
                            Surface-normal agreement:{' '}
                            {formatNumber(
                              parametricRecipe.diagnostics.agreement
                                .surface_agreement.normal_alignment * 100,
                            )}
                            % · unresolved local regions{' '}
                            {
                              parametricRecipe.diagnostics.agreement
                                .residual_regions.length
                            }
                          </small>
                        )}
                      </span>
                      <button
                        type="button"
                        className="mini-button"
                        onClick={() => void createSolidWorksExport()}
                        disabled={
                          exportingSolidWorks ||
                          !parametricRecipe.solidworks_available ||
                          parametricRecipe.diagnostics.quality
                            ?.export_recommended === false
                        }
                      >
                        {exportingSolidWorks
                          ? 'Building SLDPRT…'
                          : 'Build editable SolidWorks part'}
                      </button>
                    </div>
                    {parametricRecipe.warnings.map((warning) => (
                      <p key={warning} className="review-warning">
                        {warning}
                      </p>
                    ))}
                    {!parametricRecipe.solidworks_available && (
                      <p className="review-warning">
                        SolidWorks and its registered desktop API are required
                        to generate a native SLDPRT feature tree.
                      </p>
                    )}
                    {parametricRecipe.diagnostics.quality
                      ?.export_recommended === false && (
                      <p className="review-warning">
                        Editable CAD export is disabled because all recovered
                        feature trees are below the minimum geometric agreement.
                        Use mesh STEP while the feature beam is unsupported.
                      </p>
                    )}
                  </div>
                )}

                {solidWorksExport && (
                  <>
                    {solidWorksExport.artifact_type === 'builder_script' && (
                      <p className="review-warning">
                        SolidWorks requires this build to run in your desktop
                        session. Download and double-click the script; when it
                        finishes, the part is already open in SolidWorks. Do not
                        reopen the saved SLDPRT from Explorer while SolidWorks
                        still has it locked.
                      </p>
                    )}
                    <a
                      className="download-button"
                      href={solidWorksExport.download_url}
                      download
                    >
                      {solidWorksExport.artifact_type === 'sldprt'
                        ? 'Download editable SolidWorks SLDPRT'
                        : 'Download SolidWorks desktop builder'}
                    </a>
                  </>
                )}

                <p className="muted">
                  Fallback exports: <strong>Mesh STEP</strong> keeps the faceted
                  silhouette without history.{' '}
                  <strong>Box/cylinder STEP</strong> replaces the entire part
                  with one primitive.
                </p>
                <button
                  type="button"
                  className="control-button"
                  onClick={() => void createMeshShapeStepExport()}
                  disabled={exportingStep}
                >
                  {exportingStep
                    ? 'Building mesh STEP…'
                    : 'Export mesh shape as STEP'}
                </button>

                <p className="muted">
                  Single-primitive approximation only:
                </p>
                <div className="threshold-input">
                  <input
                    type="number"
                    min="0.01"
                    max="25"
                    step="0.1"
                    value={fitThresholdPercent}
                    onChange={(event) =>
                      setFitThresholdPercent(event.target.value)
                    }
                    aria-label="Maximum normalized RMS percent"
                  />
                  <span>% max RMS</span>
                </div>
                <button
                  type="button"
                  className="control-button"
                  onClick={runPrimitiveAnalysis}
                  disabled={analyzingPrimitives}
                >
                  {analyzingPrimitives
                    ? 'Fitting primitives…'
                    : 'Analyze box and cylinder fits'}
                </button>

                {primitiveAnalysis && (
                  <div className="primitive-results">
                    {primitiveAnalysis.fits.map((fit) => {
                      const threshold = Number(fitThresholdPercent) / 100
                      const acceptable =
                        Number.isFinite(threshold) &&
                        fit.normalized_rms <= threshold
                      return (
                        <div key={fit.primitive_type}>
                          <span>
                            <strong>{fit.primitive_type}</strong>
                            <small>{primitiveSummary(fit, record.unit!)}</small>
                            <small>
                              RMS {formatNumber(fit.rms_deviation)} {record.unit}{' '}
                              · normalized{' '}
                              {formatNumber(fit.normalized_rms * 100)}%
                            </small>
                          </span>
                          <button
                            type="button"
                            className="mini-button"
                            disabled={!acceptable || exportingStep}
                            onClick={() =>
                              createStepExport(
                                fit.primitive_type as 'box' | 'cylinder',
                              )
                            }
                          >
                            Export {fit.primitive_type} only
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}

                {stepExport && (
                  <a
                    className="download-button"
                    href={stepExport.download_url}
                    download
                  >
                    Download {stepExport.primitive_type} STEP
                  </a>
                )}
              </div>
            ) : (
              <p className="muted">
                Declare working units (section 03) to unlock mesh→CAD STEP
                export.
              </p>
            )}
          </section>

          {error && <p className="error-message">{error}</p>}

          <div className="inspector-actions">
            <button
              type="button"
              className="download-button"
              onClick={() => void openLibrary()}
            >
              Open a mesh / CAD
            </button>
            {record && (
              <>
                <a className="download-button" href={record.download_url} download>
                  Download current mesh
                </a>
                <a
                  className="download-button"
                  href={`/api/meshes/${record.id}`}
                  download={`${record.provenance.original_filename}.report.json`}
                >
                  Download JSON report
                </a>
                <label className="replace-button">
                  Replace source
                  <input
                    type="file"
                    accept=".stl,.obj,.ply"
                    onChange={handleFile}
                    disabled={uploading}
                  />
                </label>
              </>
            )}
          </div>
        </aside>
      </section>

      {libraryOpen && (
        <div className="library-overlay" role="dialog" aria-modal="true">
          <div className="library-panel">
            <div className="library-panel-heading">
              <strong>Saved meshes and STEP exports</strong>
              <button
                type="button"
                className="text-button"
                onClick={() => setLibraryOpen(false)}
              >
                Close
              </button>
            </div>
            {loadingLibrary ? (
              <p className="muted">Loading recent jobs…</p>
            ) : (
              <>
                <div className="library-section">
                  <span>Meshes</span>
                  {recentMeshes.length === 0 ? (
                    <p className="muted">No saved meshes yet.</p>
                  ) : (
                    <ul className="library-list">
                      {recentMeshes.map((mesh) => (
                        <li key={mesh.id}>
                          <button
                            type="button"
                            disabled={openingMeshId === mesh.id}
                            onClick={() => void openSavedMesh(mesh.id)}
                          >
                            <strong>{mesh.provenance.original_filename}</strong>
                            <small>
                              {geometryStateLabel(mesh)} · {sourceKindLabel(mesh)}{' '}
                              ·{' '}
                              {new Date(
                                mesh.provenance.imported_at,
                              ).toLocaleString()}
                            </small>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="library-section">
                  <span>STEP exports</span>
                  {recentExports.length === 0 ? (
                    <p className="muted">No STEP files exported yet.</p>
                  ) : (
                    <ul className="library-list">
                      {recentExports.map((item) => (
                        <li key={item.id}>
                          <a href={item.download_url} download>
                            <strong>{item.primitive_type.toUpperCase()} STEP</strong>
                            <small>
                              from {item.source_mesh_id.slice(0, 8)}… ·{' '}
                              {new Date(item.generated_at).toLocaleString()}
                            </small>
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </main>
  )
}

function Metric({
  label,
  value,
  status,
}: {
  label: string
  value: string | number
  status?: boolean
}) {
  const className =
    status === undefined ? '' : status ? 'metric-pass' : 'metric-fail'
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={className}>{value}</strong>
    </div>
  )
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 }).format(value)
}

function distanceBetween(a: Vec3, b: Vec3) {
  return Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2])
}

function formatPoint(point: Vec3) {
  return point.map((coordinate) => formatNumber(coordinate)).join(', ')
}

function artifactLabel(record: MeshRecord) {
  if (record.provenance.geometry_state === 'observed') return 'AS OBSERVED'
  if (record.provenance.geometry_state === 'reconstructed') {
    return 'PHOTOGRAMMETRY / UNSCALED'
  }
  if (record.provenance.geometry_state === 'scaled') {
    return `SCALED / ${record.unit}`
  }
  return `REPAIRED / ${record.unit ?? 'SOURCE UNITS'}`
}

function geometryStateLabel(record: MeshRecord) {
  if (record.provenance.geometry_state === 'observed') return 'Observed'
  if (record.provenance.geometry_state === 'reconstructed') {
    return 'Reconstructed'
  }
  if (record.provenance.geometry_state === 'scaled') return 'Scaled derivative'
  return 'Repaired derivative'
}

function sourceKindLabel(record: MeshRecord) {
  if (record.provenance.source_kind === 'mesh_upload') return 'Mesh upload'
  if (record.provenance.source_kind === 'photogrammetry') {
    return 'Photogrammetry'
  }
  if (record.provenance.source_kind === 'neural_reconstruction') {
    if (
      record.provenance.processing_steps.includes(
        'triposr_single_image_scaffold',
      )
    ) {
      return 'TripoSR generative scaffold'
    }
    return 'VGGT neural reconstruction'
  }
  return 'Derived artifact'
}

function primitiveSummary(fit: PrimitiveFitReport, unit: LengthUnit) {
  if (fit.primitive_type === 'box') {
    const dimensions = fit.parameters.dimensions
    if (Array.isArray(dimensions)) {
      return `${dimensions
        .map((value) => formatNumber(Number(value)))
        .join(' × ')} ${unit}`
    }
  }
  const radius = Number(fit.parameters.radius)
  const height = Number(fit.parameters.height)
  return `R ${formatNumber(radius)} × H ${formatNumber(height)} ${unit}`
}

export default App
