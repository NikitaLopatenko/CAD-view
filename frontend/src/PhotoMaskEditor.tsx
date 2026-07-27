import {
  type PointerEvent as ReactPointerEvent,
  useEffect,
  useRef,
  useState,
} from 'react'
import {
  type ForegroundBox,
  type SegmentationMode,
  previewForegroundMask,
} from './api'

interface PhotoMaskEditorProps {
  files: File[]
  samAvailable: boolean
  onCancel: () => void
  onSubmit: (masks: Blob[]) => Promise<void>
  onError: (message: string) => void
}

interface MaskResult {
  blob: Blob
  mode: SegmentationMode | 'manual'
}

type EditorTool = 'box' | 'brush' | 'eraser'

async function blankMaskBlob(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file)
  const canvas = document.createElement('canvas')
  canvas.width = bitmap.width
  canvas.height = bitmap.height
  const context = canvas.getContext('2d')
  if (!context) {
    bitmap.close()
    throw new Error('Could not create an empty mask canvas.')
  }
  context.fillStyle = '#000000'
  context.fillRect(0, 0, canvas.width, canvas.height)
  bitmap.close()
  return canvasToPngBlob(canvas)
}

function canvasToPngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob)
      else reject(new Error('Could not encode the edited mask.'))
    }, 'image/png')
  })
}

function stagePoint(
  event: ReactPointerEvent<HTMLElement>,
  stage: HTMLElement,
) {
  const bounds = stage.getBoundingClientRect()
  const width = Math.max(bounds.width, 1)
  const height = Math.max(bounds.height, 1)
  return {
    x: Math.min(1, Math.max(0, (event.clientX - bounds.left) / width)),
    y: Math.min(1, Math.max(0, (event.clientY - bounds.top) / height)),
  }
}

export function PhotoMaskEditor({
  files,
  samAvailable,
  onCancel,
  onSubmit,
  onError,
}: PhotoMaskEditorProps) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [boxes, setBoxes] = useState<(ForegroundBox | null)[]>(
    () => files.map(() => null),
  )
  const [masks, setMasks] = useState<(MaskResult | null)[]>(
    () => files.map(() => null),
  )
  const [photoUrls, setPhotoUrls] = useState<(string | null)[]>(() =>
    files.map(() => null),
  )
  const [maskUrls, setMaskUrls] = useState<(string | null)[]>(() =>
    files.map(() => null),
  )
  const [tool, setTool] = useState<EditorTool>('box')
  const [brushSize, setBrushSize] = useState(36)
  const [generatingIndex, setGeneratingIndex] = useState<number | null>(null)
  const [batchGenerating, setBatchGenerating] = useState(false)
  const [starting, setStarting] = useState(false)
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null)

  const stageRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const paintingRef = useRef(false)
  const lastPaintRef = useRef<{ x: number; y: number } | null>(null)
  const boxDragRef = useRef<{ x: number; y: number } | null>(null)
  const maskRevisionRef = useRef(0)

  useEffect(() => {
    let cancelled = false
    const urls = files.map((file) => URL.createObjectURL(file))
    queueMicrotask(() => {
      if (!cancelled) setPhotoUrls(urls)
    })
    return () => {
      cancelled = true
      urls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [files])

  useEffect(() => {
    let cancelled = false
    const urls = masks.map((mask) =>
      mask ? URL.createObjectURL(mask.blob) : null,
    )
    queueMicrotask(() => {
      if (!cancelled) setMaskUrls(urls)
    })
    return () => {
      cancelled = true
      urls.forEach((url) => {
        if (url) URL.revokeObjectURL(url)
      })
    }
  }, [masks])

  useEffect(() => {
    const canvas = canvasRef.current
    const mask = masks[activeIndex]
    if (!canvas) return
    const target = canvas

    let cancelled = false
    const revision = ++maskRevisionRef.current

    async function syncCanvas() {
      if (!mask) {
        const context = target.getContext('2d')
        if (context) {
          context.clearRect(0, 0, target.width, target.height)
        }
        return
      }
      const bitmap = await createImageBitmap(mask.blob)
      if (cancelled || revision !== maskRevisionRef.current) {
        bitmap.close()
        return
      }
      target.width = bitmap.width
      target.height = bitmap.height
      const context = target.getContext('2d')
      if (!context) {
        bitmap.close()
        return
      }
      context.clearRect(0, 0, target.width, target.height)
      context.drawImage(bitmap, 0, 0)
      bitmap.close()
    }

    void syncCanvas()
    return () => {
      cancelled = true
    }
  }, [activeIndex, masks])

  function canvasCoords(event: ReactPointerEvent<HTMLElement>) {
    const stage = stageRef.current
    const canvas = canvasRef.current
    if (!stage || !canvas || canvas.width === 0 || canvas.height === 0) {
      return null
    }
    const point = stagePoint(event, stage)
    return {
      x: point.x * canvas.width,
      y: point.y * canvas.height,
      normalized: point,
    }
  }

  function paintAt(x: number, y: number) {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return
    const radius = Math.max(1, (brushSize / 100) * Math.min(canvas.width, canvas.height) * 0.08)
    context.save()
    context.lineCap = 'round'
    context.lineJoin = 'round'
    context.strokeStyle = tool === 'eraser' ? '#000000' : '#ffffff'
    context.fillStyle = tool === 'eraser' ? '#000000' : '#ffffff'
    context.lineWidth = radius * 2
    const previous = lastPaintRef.current
    if (previous) {
      context.beginPath()
      context.moveTo(previous.x, previous.y)
      context.lineTo(x, y)
      context.stroke()
    } else {
      context.beginPath()
      context.arc(x, y, radius, 0, Math.PI * 2)
      context.fill()
    }
    context.restore()
    lastPaintRef.current = { x, y }
  }

  async function commitCanvasMask(_mode: MaskResult['mode'] = 'manual') {
    const canvas = canvasRef.current
    if (!canvas || canvas.width === 0 || canvas.height === 0) return
    const blob = await canvasToPngBlob(canvas)
    setMasks((previous) => {
      const next = [...previous]
      next[activeIndex] = { blob, mode: 'manual' }
      return next
    })
  }

  async function generateMask(index: number, box: ForegroundBox) {
    setGeneratingIndex(index)
    try {
      const result = await previewForegroundMask(files[index], box)
      setMasks((previous) => {
        const next = [...previous]
        next[index] = result
        return next
      })
      setTool('brush')
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Segmentation failed.')
      throw error
    } finally {
      setGeneratingIndex(null)
    }
  }

  async function finishBoxDrag(event: ReactPointerEvent<HTMLDivElement>) {
    const start = boxDragRef.current
    if (!start) return
    const stage = stageRef.current
    if (!stage) return
    const current = stagePoint(event, stage)
    const box = {
      x_min: Math.min(start.x, current.x),
      y_min: Math.min(start.y, current.y),
      x_max: Math.max(start.x, current.x),
      y_max: Math.max(start.y, current.y),
    }
    setBoxes((previous) => {
      const next = [...previous]
      next[activeIndex] = box
      return next
    })
    boxDragRef.current = null
    event.currentTarget.releasePointerCapture(event.pointerId)
    if (box.x_max - box.x_min > 0.01 && box.y_max - box.y_min > 0.01) {
      await generateMask(activeIndex, box)
    }
  }

  async function applyBoxToAll() {
    const source = boxes[activeIndex]
    if (!source) return
    setBatchGenerating(true)
    setBoxes(files.map(() => source))
    try {
      for (let index = 0; index < files.length; index += 1) {
        await generateMask(index, source)
      }
    } finally {
      setBatchGenerating(false)
    }
  }

  async function clearActiveMask() {
    const image = imageRef.current
    const canvas = canvasRef.current
    try {
      if (canvas && image?.naturalWidth) {
        canvas.width = image.naturalWidth
        canvas.height = image.naturalHeight
        const context = canvas.getContext('2d')
        if (!context) throw new Error('Could not clear mask canvas.')
        context.fillStyle = '#000000'
        context.fillRect(0, 0, canvas.width, canvas.height)
        await commitCanvasMask('manual')
        return
      }
      const blob = await blankMaskBlob(files[activeIndex])
      setMasks((previous) => {
        const next = [...previous]
        next[activeIndex] = { blob, mode: 'manual' }
        return next
      })
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Could not clear mask.')
    }
  }

  async function startReconstruction() {
    if (masks.some((mask) => !mask)) return
    setStarting(true)
    try {
      await onSubmit(masks.map((mask) => mask!.blob))
    } finally {
      setStarting(false)
    }
  }

  async function onStagePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (busy || !photoUrls[activeIndex]) return
    if (tool === 'box') {
      boxDragRef.current = stagePoint(event, event.currentTarget)
      event.currentTarget.setPointerCapture(event.pointerId)
      return
    }

    const canvas = canvasRef.current
    const image = imageRef.current
    if (!canvas || !image?.naturalWidth) return

    if (
      canvas.width !== image.naturalWidth ||
      canvas.height !== image.naturalHeight
    ) {
      canvas.width = image.naturalWidth
      canvas.height = image.naturalHeight
      const context = canvas.getContext('2d')
      if (!context) return
      if (masks[activeIndex]) {
        const bitmap = await createImageBitmap(masks[activeIndex]!.blob)
        context.drawImage(bitmap, 0, 0)
        bitmap.close()
      } else {
        context.fillStyle = '#000000'
        context.fillRect(0, 0, canvas.width, canvas.height)
      }
    } else if (!masks[activeIndex]) {
      const context = canvas.getContext('2d')
      if (!context) return
      context.fillStyle = '#000000'
      context.fillRect(0, 0, canvas.width, canvas.height)
    }

    const point = canvasCoords(event)
    if (!point) return
    paintingRef.current = true
    lastPaintRef.current = null
    event.currentTarget.setPointerCapture(event.pointerId)
    paintAt(point.x, point.y)
  }

  function onStagePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const stage = stageRef.current
    if (stage) setCursor(stagePoint(event, stage))

    if (tool === 'box') {
      const start = boxDragRef.current
      if (!start) return
      const current = stagePoint(event, event.currentTarget)
      setBoxes((previous) => {
        const next = [...previous]
        next[activeIndex] = {
          x_min: Math.min(start.x, current.x),
          y_min: Math.min(start.y, current.y),
          x_max: Math.max(start.x, current.x),
          y_max: Math.max(start.y, current.y),
        }
        return next
      })
      return
    }

    if (!paintingRef.current) return
    const point = canvasCoords(event)
    if (!point) return
    paintAt(point.x, point.y)
  }

  async function onStagePointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    if (tool === 'box') {
      await finishBoxDrag(event)
      return
    }
    if (!paintingRef.current) return
    paintingRef.current = false
    lastPaintRef.current = null
    event.currentTarget.releasePointerCapture(event.pointerId)
    await commitCanvasMask()
  }

  const activeBox = boxes[activeIndex]
  const reviewedCount = masks.filter(Boolean).length
  const busy = generatingIndex !== null || batchGenerating || starting
  const activePhotoUrl = photoUrls[activeIndex]
  const activeMask = masks[activeIndex]
  const brushCursorSize = Math.max(10, brushSize)

  return (
    <div className="mask-editor">
      <div className="mask-editor-heading">
        <div>
          <strong>Isolate the reconstruction target</strong>
          <small>
            Draw a box for SAM, then refine with brush/eraser. Leave a little
            surrounding texture if the object is glossy or plain.
          </small>
        </div>
        <span>
          {reviewedCount}/{files.length} reviewed
        </span>
      </div>

      <div className="mask-tool-row">
        <button
          type="button"
          className={`control-button${tool === 'box' ? ' active' : ''}`}
          disabled={busy}
          onClick={() => setTool('box')}
        >
          Box
        </button>
        <button
          type="button"
          className={`control-button${tool === 'brush' ? ' active' : ''}`}
          disabled={busy}
          onClick={() => setTool('brush')}
        >
          Brush
        </button>
        <button
          type="button"
          className={`control-button${tool === 'eraser' ? ' active' : ''}`}
          disabled={busy}
          onClick={() => setTool('eraser')}
        >
          Eraser
        </button>
        <label className="brush-size">
          Size
          <input
            type="range"
            min={8}
            max={100}
            value={brushSize}
            disabled={busy || tool === 'box'}
            onChange={(event) => setBrushSize(Number(event.target.value))}
          />
        </label>
      </div>

      <div
        ref={stageRef}
        className={`mask-stage tool-${tool}`}
        onPointerDown={(event) => void onStagePointerDown(event)}
        onPointerMove={onStagePointerMove}
        onPointerUp={(event) => void onStagePointerUp(event)}
        onPointerLeave={() => setCursor(null)}
      >
        {activePhotoUrl ? (
          <img
            ref={imageRef}
            src={activePhotoUrl}
            alt={`Photo ${activeIndex + 1}`}
            draggable={false}
          />
        ) : (
          <div className="mask-stage-placeholder">Loading photo…</div>
        )}
        <canvas ref={canvasRef} className="mask-paint-canvas" />
        {activeBox && tool === 'box' && (
          <span
            className="mask-box"
            style={{
              left: `${activeBox.x_min * 100}%`,
              top: `${activeBox.y_min * 100}%`,
              width: `${(activeBox.x_max - activeBox.x_min) * 100}%`,
              height: `${(activeBox.y_max - activeBox.y_min) * 100}%`,
            }}
          />
        )}
        {cursor && tool !== 'box' && (
          <span
            className="brush-cursor"
            style={{
              left: `${cursor.x * 100}%`,
              top: `${cursor.y * 100}%`,
              width: brushCursorSize,
              height: brushCursorSize,
            }}
          />
        )}
        {generatingIndex === activeIndex && (
          <span className="mask-working">Generating mask…</span>
        )}
      </div>

      <div className="mask-toolbar">
        <button
          type="button"
          className="control-button"
          disabled={!activeBox || busy}
          onClick={() => activeBox && void generateMask(activeIndex, activeBox)}
        >
          Regenerate from box
        </button>
        <button
          type="button"
          className="control-button"
          disabled={!activeBox || busy}
          onClick={() => void applyBoxToAll()}
        >
          Apply box to all
        </button>
        <button
          type="button"
          className="control-button"
          disabled={busy}
          onClick={() => void clearActiveMask()}
        >
          Clear mask
        </button>
        <small>
          {!activeMask
            ? tool === 'box'
              ? 'Drag a box over the object.'
              : 'Paint the object, or start with a box.'
            : activeMask.mode === 'manual'
              ? 'Manual mask edits'
              : activeMask.mode === 'rectangle_fallback'
                ? 'Rectangle seed — refine with brush/eraser.'
                : samAvailable
                  ? 'SAM 2 seed — refine with brush/eraser.'
                  : 'Seed mask ready for edits.'}
        </small>
      </div>

      <div className="mask-filmstrip">
        {files.map((file, index) => (
          <button
            type="button"
            className={index === activeIndex ? 'active' : ''}
            key={`${file.name}-${file.size}-${file.lastModified}-${index}`}
            onClick={() => setActiveIndex(index)}
          >
            {photoUrls[index] ? (
              <img src={photoUrls[index]!} alt="" />
            ) : (
              <span className="mask-thumb-placeholder" />
            )}
            {maskUrls[index] && (
              <img className="mask-overlay" src={maskUrls[index]!} alt="" />
            )}
            <span>{index + 1}</span>
          </button>
        ))}
      </div>

      <div className="mask-actions">
        <button
          type="button"
          className="text-button"
          disabled={busy}
          onClick={onCancel}
        >
          Cancel photo set
        </button>
        <button
          type="button"
          className="control-button primary"
          disabled={reviewedCount !== files.length || busy}
          onClick={() => void startReconstruction()}
        >
          {starting ? 'Uploading…' : 'Use reviewed masks'}
        </button>
      </div>
    </div>
  )
}
