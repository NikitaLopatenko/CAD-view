export type Vec3 = [number, number, number]

export interface Qualification {
  vertex_count: number
  face_count: number
  connected_components: number
  is_watertight: boolean
  is_winding_consistent: boolean
  euler_number: number
  bounds: {
    minimum: Vec3
    maximum: Vec3
  }
  extents: Vec3
  volume: number | null
}

export interface MeshRecord {
  id: string
  extension: '.stl' | '.obj' | '.ply'
  download_url: string
  unit: LengthUnit | null
  qualification: Qualification
  provenance: {
    source_kind:
      | 'mesh_upload'
      | 'photogrammetry'
      | 'neural_reconstruction'
      | 'derived'
    original_filename: string
    sha256: string
    byte_size: number
    imported_at: string
    geometry_state: 'observed' | 'reconstructed' | 'scaled' | 'repaired'
    parent_id: string | null
    processing_steps: string[]
  }
  scale_application: ScaleApplication | null
  repair_report: RepairReport | null
  check_constraints: CheckConstraint[]
}

export type LengthUnit = 'mm' | 'cm' | 'm' | 'in'

export interface ScaleApplication {
  point_a: Vec3
  point_b: Vec3
  measured_distance_source: number
  target_distance: number
  unit: LengthUnit
  scale_factor: number
  residual: number
}

export interface ScaleRequest {
  point_a: Vec3
  point_b: Vec3
  target_distance: number
  unit: LengthUnit
}

export interface RepairReport {
  before: Qualification
  after: Qualification
  duplicate_faces_removed: number
  faces_added: number
  winding_reoriented: boolean
  fill_small_holes_requested: boolean
  net_surface_area_change: number
  max_existing_vertex_displacement: number
  requires_human_review: boolean
}

export interface CheckConstraint {
  id: string
  label: string
  point_a: Vec3
  point_b: Vec3
  measured_distance: number
  expected_distance: number
  tolerance: number
  unit: LengthUnit
  residual: number
  relative_error_percent: number
  passes: boolean
  checked_at: string
}

export interface CheckConstraintRequest {
  label: string
  point_a: Vec3
  point_b: Vec3
  expected_distance: number
  tolerance: number
}

export type ReconstructionEngineChoice = 'auto' | 'meshroom' | 'vggt'

export interface ReconstructionCapabilities {
  engine: 'dual' | 'meshroom'
  engines: ReconstructionEngineChoice[]
  available: boolean
  meshroom_available?: boolean
  executable: string | null
  supports_photos: boolean
  supports_video: boolean
  minimum_image_count: number
  provenance_class: 'photogrammetry_reconstructed'
  segmentation_available: boolean
  segmentation_engine: 'sam2' | 'rectangle_fallback'
  segmentation_model: string | null
  neural_engine?: 'vggt'
  neural_available?: boolean
  neural_source_ready?: boolean
  neural_model?: string
}

export interface ForegroundBox {
  x_min: number
  y_min: number
  x_max: number
  y_max: number
}

export type SegmentationMode = 'sam2' | 'rectangle_fallback'

export interface CameraIntrinsicReport {
  make: string | null
  model: string | null
  focal_length_mm: number | null
  focal_length_35mm: number | null
  sensor_width_mm: number | null
  image_width: number | null
  image_height: number | null
  horizontal_fov_deg: number | null
  source: string
  shared_intrinsic_recommended: boolean
  notes: string[]
}

export interface ReconstructionJob {
  id: string
  engine: ReconstructionEngineChoice
  resolved_engine: 'meshroom' | 'vggt' | null
  input_kind: 'photo_set' | 'video'
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  stage: string
  input_count: number
  output_mesh_id: string | null
  camera: CameraIntrinsicReport | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface PrimitiveFitReport {
  primitive_type: 'box' | 'cylinder' | 'mesh_solid'
  parameters: Record<string, unknown>
  rms_deviation: number
  max_deviation: number
  normalized_rms: number
}

export interface PrimitiveAnalysis {
  mesh_id: string
  unit: LengthUnit | null
  fits: PrimitiveFitReport[]
}

export interface StepExportRecord {
  id: string
  source_mesh_id: string
  primitive_type: 'box' | 'cylinder' | 'mesh_solid'
  unit: LengthUnit
  fit: PrimitiveFitReport
  download_url: string
  generated_at: string
}

export interface ParametricSketch {
  name: string
  plane: string
  outer_loop: {
    kind: 'polyline'
    points: [number, number][]
  }
  inner_loops: Array<
    | {
        kind: 'circle'
        center: [number, number]
        radius: number
        fit_normalized_rms: number
      }
    | {
        kind: 'polyline'
        points: [number, number][]
      }
  >
}

export interface ParametricFeature {
  id: string
  name: string
  type: 'extrude' | 'cut' | 'sweep_cut'
  depth: number
  start_offset: number
  role:
    | 'base'
    | 'perimeter_groove_flange'
    | 'perimeter_groove_cut'
    | 'perimeter_groove_sweep'
  sketch?: ParametricSketch
  profile?: ParametricSketch
  path?: {
    name: string
    plane: string
    kind: 'polyline'
    points: [number, number][]
    closed: boolean
  }
}

export interface ParametricDeviation {
  sample_count: number
  mean: number | null
  rms: number | null
  p95: number | null
  max: number | null
}

export interface SweepCandidate {
  id: string
  type: 'perimeter_groove'
  classification: 'variable_profile_sweep' | 'constant_profile_sweep'
  section: {
    axial_width: number
    average_radial_depth: number
    maximum_radial_depth: number
  }
  confidence: number
  solidworks_representation:
    | 'two_native_side_boss_extrudes'
    | 'outer_extrude_plus_native_cut'
    | 'native_sweep_cut'
  intent_analysis?: OrthogonalSweepAnalysis
}

export interface FeatureHypothesis {
  type: 'sweep_cut' | 'stacked_cut'
  score: number
  deviation_rms: number
  complexity_penalty: number
}

export interface OrthogonalSweepAnalysis {
  selected: boolean
  decision:
    | 'ambiguous_equivalent'
    | 'sweep_preferred'
    | 'sweep_preferred_low_confidence'
    | 'stacked_preferred'
    | 'stacked_preferred_low_confidence'
  score_delta: number
  coverage: number
  station_count: number
  maximum_depth: number
  sweep_rms: number
  sweep_normalized_rms: number
  stacked_rms: number
  stacked_normalized_rms: number
  hypotheses: FeatureHypothesis[]
}

export interface ParametricDiagnostics {
  groove_detected: boolean
  groove_width: number
  flange_depth: number
  section_variation_fraction: number
  side_symmetry_error: number
  sweep_candidates: SweepCandidate[]
  feature_intent: {
    selected: 'extrude' | 'stacked_cut' | 'sweep_cut'
    orthogonal_section_analysis: OrthogonalSweepAnalysis | null
  }
  deviation: ParametricDeviation
  volume_error_percent: number | null
  [key: string]: unknown
}

export interface ParametricRecipeReport {
  mesh_id: string
  unit: LengthUnit
  strategy:
    | 'prismatic_extrusion'
    | 'multi_section_perimeter_groove'
    | 'sweep_cut_reconstruction'
  confidence: number
  features: ParametricFeature[]
  diagnostics: ParametricDiagnostics
  warnings: string[]
  solidworks_available: boolean
}

export interface SolidWorksExportRecord {
  id: string
  source_mesh_id: string
  strategy: string
  confidence: number
  feature_count: number
  unit: LengthUnit
  artifact_type: 'sldprt' | 'builder_script'
  download_url: string
  generated_at: string
  warnings: string[]
}

interface ApiErrorBody {
  detail?: string
}

export async function listMeshes() {
  const response = await fetch('/api/meshes')
  if (!response.ok) throw new Error('Could not list saved meshes.')
  return response.json() as Promise<MeshRecord[]>
}

export async function listExports() {
  const response = await fetch('/api/exports')
  if (!response.ok) throw new Error('Could not list STEP exports.')
  return response.json() as Promise<StepExportRecord[]>
}

export async function uploadMesh(file: File): Promise<MeshRecord> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch('/api/meshes', {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(body.detail ?? `Upload failed with status ${response.status}.`)
  }

  return response.json() as Promise<MeshRecord>
}

export async function declareMeshUnits(
  meshId: string,
  unit: LengthUnit,
): Promise<MeshRecord> {
  const response = await fetch(`/api/meshes/${meshId}/units`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ unit }),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(
      body.detail ?? `Could not declare units (${response.status}).`,
    )
  }

  return response.json() as Promise<MeshRecord>
}

export async function scaleMesh(
  meshId: string,
  request: ScaleRequest,
): Promise<MeshRecord> {
  const response = await fetch(`/api/meshes/${meshId}/scale`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(body.detail ?? `Scaling failed with status ${response.status}.`)
  }

  return response.json() as Promise<MeshRecord>
}

export async function repairMesh(
  meshId: string,
  fillSmallHoles: boolean,
): Promise<MeshRecord> {
  const response = await fetch(`/api/meshes/${meshId}/repair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fill_small_holes: fillSmallHoles }),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(body.detail ?? `Repair failed with status ${response.status}.`)
  }

  return response.json() as Promise<MeshRecord>
}

export async function addCheckConstraint(
  meshId: string,
  request: CheckConstraintRequest,
): Promise<MeshRecord> {
  const response = await fetch(`/api/meshes/${meshId}/checks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(
      body.detail ?? `Dimensional check failed with status ${response.status}.`,
    )
  }

  return response.json() as Promise<MeshRecord>
}

export async function getReconstructionCapabilities() {
  const response = await fetch('/api/reconstructions/capabilities')
  if (!response.ok) throw new Error('Could not read reconstruction capabilities.')
  return response.json() as Promise<ReconstructionCapabilities>
}

export async function previewForegroundMask(
  file: File,
  box: ForegroundBox,
) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('box', JSON.stringify(box))
  const response = await fetch('/api/reconstructions/mask-preview', {
    method: 'POST',
    body: formData,
  })
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(error.detail ?? 'Foreground segmentation failed.')
  }
  return {
    blob: await response.blob(),
    mode: (response.headers.get('X-Segmentation-Mode') ??
      'rectangle_fallback') as SegmentationMode,
  }
}

export async function createPhotoReconstruction(
  files: File[],
  masks?: Blob[],
  engine: ReconstructionEngineChoice = 'auto',
) {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  masks?.forEach((mask, index) =>
    formData.append(
      'masks',
      mask,
      `mask-${String(index + 1).padStart(4, '0')}.png`,
    ),
  )
  formData.append('engine', engine)
  return createReconstruction('/api/reconstructions/photos', formData)
}

export async function createVideoReconstruction(
  file: File,
  engine: ReconstructionEngineChoice = 'auto',
) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('engine', engine)
  return createReconstruction('/api/reconstructions/video', formData)
}

async function createReconstruction(url: string, body: FormData) {
  const response = await fetch(url, { method: 'POST', body })
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(error.detail ?? `Reconstruction request failed (${response.status}).`)
  }
  return response.json() as Promise<ReconstructionJob>
}

export async function getReconstructionJob(jobId: string) {
  const response = await fetch(`/api/reconstructions/${jobId}`)
  if (!response.ok) throw new Error('Could not read reconstruction status.')
  return response.json() as Promise<ReconstructionJob>
}

export async function getMesh(meshId: string) {
  const response = await fetch(`/api/meshes/${meshId}`)
  if (!response.ok) throw new Error('Could not load reconstructed mesh.')
  return response.json() as Promise<MeshRecord>
}

export async function analyzePrimitives(meshId: string) {
  const response = await fetch(`/api/meshes/${meshId}/primitives`)
  if (!response.ok) throw new Error('Primitive analysis failed.')
  return response.json() as Promise<PrimitiveAnalysis>
}

export async function exportPrimitiveStep(
  meshId: string,
  primitiveType: 'box' | 'cylinder',
  maxNormalizedRms: number,
) {
  const response = await fetch(`/api/meshes/${meshId}/step`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      primitive_type: primitiveType,
      max_normalized_rms: maxNormalizedRms,
    }),
  })
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(error.detail ?? 'STEP export failed.')
  }
  return response.json() as Promise<StepExportRecord>
}

export async function exportMeshShapeStep(meshId: string) {
  const response = await fetch(`/api/meshes/${meshId}/step/mesh`, {
    method: 'POST',
  })
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(error.detail ?? 'Mesh STEP export failed.')
  }
  return response.json() as Promise<StepExportRecord>
}

export async function analyzeParametricRecipe(meshId: string) {
  const response = await fetch(`/api/meshes/${meshId}/parametric`)
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(error.detail ?? 'Parametric feature analysis failed.')
  }
  return response.json() as Promise<ParametricRecipeReport>
}

export async function exportSolidWorksPart(
  meshId: string,
  visible = false,
) {
  const response = await fetch(`/api/meshes/${meshId}/solidworks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ visible }),
  })
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(error.detail ?? 'SolidWorks feature-tree export failed.')
  }
  return response.json() as Promise<SolidWorksExportRecord>
}
