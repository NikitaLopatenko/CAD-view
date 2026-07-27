import { Bounds, Grid, OrbitControls } from '@react-three/drei'
import { Canvas, type ThreeEvent, useLoader } from '@react-three/fiber'
import { Suspense, useMemo } from 'react'
import { Mesh, MeshStandardMaterial } from 'three'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import type { Vec3 } from './api'

interface MeshViewerProps {
  extension: '.stl' | '.obj' | '.ply'
  url: string
  extents: Vec3
  selectedPoints: Vec3[]
  selectionEnabled: boolean
  onPointPick: (point: Vec3) => void
}

interface ModelProps {
  url: string
  onPointPick: (event: ThreeEvent<MouseEvent>) => void
}

function StlModel({ url, onPointPick }: ModelProps) {
  const source = useLoader(STLLoader, url)
  const geometry = useMemo(() => {
    const cloned = source.clone()
    cloned.computeVertexNormals()
    return cloned
  }, [source])

  return (
    <mesh
      geometry={geometry}
      castShadow
      receiveShadow
      onClick={onPointPick}
    >
      <meshStandardMaterial color="#87a9c4" roughness={0.68} metalness={0.08} />
    </mesh>
  )
}

function PlyModel({ url, onPointPick }: ModelProps) {
  const source = useLoader(PLYLoader, url)
  const geometry = useMemo(() => {
    const cloned = source.clone()
    cloned.computeVertexNormals()
    return cloned
  }, [source])

  return (
    <mesh
      geometry={geometry}
      castShadow
      receiveShadow
      onClick={onPointPick}
    >
      <meshStandardMaterial color="#87a9c4" roughness={0.68} metalness={0.08} />
    </mesh>
  )
}

function ObjModel({ url, onPointPick }: ModelProps) {
  const source = useLoader(OBJLoader, url)
  const object = useMemo(() => {
    const cloned = source.clone()
    cloned.traverse((child) => {
      if (child instanceof Mesh) {
        child.material = new MeshStandardMaterial({
          color: '#87a9c4',
          roughness: 0.68,
          metalness: 0.08,
        })
        child.castShadow = true
        child.receiveShadow = true
      }
    })
    return cloned
  }, [source])

  return <primitive object={object} onClick={onPointPick} />
}

function Model({
  extension,
  url,
  onPointPick,
}: Pick<MeshViewerProps, 'extension' | 'url'> & {
  onPointPick: (event: ThreeEvent<MouseEvent>) => void
}) {
  if (extension === '.obj') {
    return <ObjModel url={url} onPointPick={onPointPick} />
  }
  if (extension === '.ply') {
    return <PlyModel url={url} onPointPick={onPointPick} />
  }
  return <StlModel url={url} onPointPick={onPointPick} />
}

export function MeshViewer({
  extension,
  url,
  extents,
  selectedPoints,
  selectionEnabled,
  onPointPick,
}: MeshViewerProps) {
  const markerRadius = Math.max(...extents) * 0.014

  function handlePointPick(event: ThreeEvent<MouseEvent>) {
    if (!selectionEnabled) return
    event.stopPropagation()
    onPointPick([event.point.x, event.point.y, event.point.z])
  }

  return (
    <Canvas
      camera={{ position: [4, 3, 5], fov: 42 }}
      dpr={[1, 2]}
      gl={{ antialias: true }}
      style={{ cursor: selectionEnabled ? 'crosshair' : 'grab' }}
    >
      <color attach="background" args={['#11161b']} />
      <ambientLight intensity={1.4} />
      <directionalLight position={[4, 8, 6]} intensity={2.2} />
      <directionalLight position={[-5, 2, -4]} intensity={0.8} />
      <Suspense fallback={null}>
        <Bounds fit clip observe margin={1.35}>
          <Model
            extension={extension}
            url={url}
            onPointPick={handlePointPick}
          />
          {selectedPoints.map((point, index) => (
            <mesh key={index} position={point}>
              <sphereGeometry args={[markerRadius, 20, 12]} />
              <meshBasicMaterial color={index === 0 ? '#ffb454' : '#67d7bd'} />
            </mesh>
          ))}
        </Bounds>
      </Suspense>
      <Grid
        infiniteGrid
        fadeDistance={100}
        fadeStrength={4}
        cellSize={1}
        sectionSize={10}
        cellColor="#2f3c45"
        sectionColor="#48606f"
        position={[0, -1, 0]}
      />
      <OrbitControls makeDefault />
    </Canvas>
  )
}
