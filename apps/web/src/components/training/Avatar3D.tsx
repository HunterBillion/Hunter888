"use client";

import { useRef, useMemo, useState, useEffect, useCallback } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";

import { EMOTION_MAP, type EmotionState } from "@/types";
import { JarvisScene } from "./JarvisCore";
import { useReducedMotion } from "@/hooks/useReducedMotion";

// ─── Emotion config ──────────────────────────────────────────────────────────

const EMOTION_COLORS: Record<string, string> = Object.fromEntries(
  Object.entries(EMOTION_MAP).map(([k, v]) => [k, v.color]),
);

const EMOTION_SPEEDS: Record<string, number> = {
  cold: 0.3,
  skeptical: 0.4,
  warming: 0.6,
  open: 0.7,
  deal: 0.8,
};

// Eye shape per emotion: [scaleX, scaleY]
const EYE_SHAPES: Record<string, [number, number]> = {
  cold: [1.0, 0.4],
  skeptical: [1.0, 0.5],
  warming: [1.0, 0.8],
  open: [1.0, 1.0],
  deal: [1.2, 0.6],
};

// Mouth curve per emotion: positive = smile, negative = frown
const MOUTH_CURVES: Record<string, number> = {
  cold: -0.15,
  skeptical: -0.05,
  warming: 0.05,
  open: 0.1,
  deal: 0.25,
};

// Brow angle per emotion: positive = raised, negative = furrowed
const BROW_ANGLES: Record<string, number> = {
  cold: -0.12,
  skeptical: -0.08,
  warming: 0.02,
  open: 0.06,
  deal: 0.1,
};

// ─── Color lerp helper ──────────────────────────────────────────────────────

const _colorA = new THREE.Color();
const _colorB = new THREE.Color();

function lerpColor(current: THREE.Color, target: string, speed: number) {
  _colorB.set(target);
  current.lerp(_colorB, speed);
}

// ─── Face features ──────────────────────────────────────────────────────────

function FaceFeatures({ emotion, isSpeaking, audioLevel }: {
  emotion: string;
  isSpeaking: boolean;
  audioLevel: number;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const leftEyeRef = useRef<THREE.Mesh>(null);
  const rightEyeRef = useRef<THREE.Mesh>(null);
  const mouthRef = useRef<THREE.Group>(null);
  const pupilLeftRef = useRef<THREE.Mesh>(null);
  const pupilRightRef = useRef<THREE.Mesh>(null);
  const irisLeftRef = useRef<THREE.Mesh>(null);
  const irisRightRef = useRef<THREE.Mesh>(null);
  const leftBrowRef = useRef<THREE.Group>(null);
  const rightBrowRef = useRef<THREE.Group>(null);

  const eyeShape = EYE_SHAPES[emotion] || EYE_SHAPES.cold;
  const mouthCurve = MOUTH_CURVES[emotion] || 0;
  const browAngle = BROW_ANGLES[emotion] || 0;
  const color = EMOTION_COLORS[emotion] || EMOTION_COLORS.cold;

  // Smooth color transition for eyes
  const eyeColor = useRef(new THREE.Color(color));

  const mouthPoints = useMemo(() => {
    const curve = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(-0.25, 0, 0),
      new THREE.Vector3(0, -mouthCurve, 0),
      new THREE.Vector3(0.25, 0, 0),
    );
    return curve.getPoints(20).map((p) => [p.x, p.y, p.z] as [number, number, number]);
  }, [mouthCurve]);

  // Brow curve points
  const browPoints = useMemo(() => {
    const curve = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(-0.08, 0, 0),
      new THREE.Vector3(0, browAngle, 0),
      new THREE.Vector3(0.08, 0, 0),
    );
    return curve.getPoints(12).map((p) => [p.x, p.y, p.z] as [number, number, number]);
  }, [browAngle]);

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const t = clock.elapsedTime;

    // Smooth color transition
    lerpColor(eyeColor.current, color, 0.04);

    // Idle blink every ~4-6 seconds
    const blinkCycle = Math.sin(t * 0.8) * Math.sin(t * 1.3);
    const blink = blinkCycle > 0.95 ? 0.1 : 1.0;

    const [sx, sy] = eyeShape;
    if (leftEyeRef.current) {
      leftEyeRef.current.scale.set(sx, sy * blink, 1);
      (leftEyeRef.current.material as THREE.MeshBasicMaterial).color.copy(eyeColor.current);
    }
    if (rightEyeRef.current) {
      rightEyeRef.current.scale.set(sx, sy * blink, 1);
      (rightEyeRef.current.material as THREE.MeshBasicMaterial).color.copy(eyeColor.current);
    }

    // Iris glow pulse
    if (irisLeftRef.current) {
      const mat = irisLeftRef.current.material as THREE.MeshBasicMaterial;
      mat.color.copy(eyeColor.current);
      mat.opacity = 0.3 + Math.sin(t * 2) * 0.1;
    }
    if (irisRightRef.current) {
      const mat = irisRightRef.current.material as THREE.MeshBasicMaterial;
      mat.color.copy(eyeColor.current);
      mat.opacity = 0.3 + Math.sin(t * 2) * 0.1;
    }

    // Pupil micro-movement
    const lookX = Math.sin(t * 0.5) * 0.02;
    const lookY = Math.cos(t * 0.7) * 0.015;
    if (pupilLeftRef.current) {
      pupilLeftRef.current.position.set(-0.28 + lookX, 0.2 + lookY, 1.18);
    }
    if (pupilRightRef.current) {
      pupilRightRef.current.position.set(0.28 + lookX, 0.2 + lookY, 1.18);
    }

    // Mouth animation
    if (mouthRef.current) {
      if (isSpeaking) {
        const openAmount = 0.03 + audioLevel * 0.08 + Math.sin(t * 8) * 0.02;
        mouthRef.current.position.y = -0.25 - openAmount;
        mouthRef.current.scale.set(1, 1 + audioLevel * 2, 1);
      } else {
        mouthRef.current.position.y = -0.25;
        mouthRef.current.scale.set(1, 1, 1);
      }
    }

    // Brow subtle animation
    if (leftBrowRef.current) {
      leftBrowRef.current.rotation.z = Math.sin(t * 0.3) * 0.02;
    }
    if (rightBrowRef.current) {
      rightBrowRef.current.rotation.z = -Math.sin(t * 0.3) * 0.02;
    }
  });

  return (
    <group ref={groupRef} position={[0, 0, 0]}>
      {/* Left eye — outer glow ring */}
      <mesh position={[-0.28, 0.2, 1.08]}>
        <ringGeometry args={[0.075, 0.095, 24]} />
        <meshBasicMaterial color={color} transparent opacity={0.25} />
      </mesh>
      {/* Left eye */}
      <mesh ref={leftEyeRef} position={[-0.28, 0.2, 1.1]}>
        <circleGeometry args={[0.08, 24]} />
        <meshBasicMaterial color={color} transparent opacity={0.9} />
      </mesh>
      {/* Left iris ring */}
      <mesh ref={irisLeftRef} position={[-0.28, 0.2, 1.13]}>
        <ringGeometry args={[0.035, 0.055, 20]} />
        <meshBasicMaterial color={color} transparent opacity={0.35} />
      </mesh>
      {/* Left pupil */}
      <mesh ref={pupilLeftRef} position={[-0.28, 0.2, 1.18]}>
        <circleGeometry args={[0.03, 16]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.95} />
      </mesh>
      {/* Left pupil core (bright dot) */}
      <mesh position={[-0.28, 0.2, 1.19]}>
        <circleGeometry args={[0.012, 12]} />
        <meshBasicMaterial color="#ffffff" />
      </mesh>

      {/* Right eye — outer glow ring */}
      <mesh position={[0.28, 0.2, 1.08]}>
        <ringGeometry args={[0.075, 0.095, 24]} />
        <meshBasicMaterial color={color} transparent opacity={0.25} />
      </mesh>
      {/* Right eye */}
      <mesh ref={rightEyeRef} position={[0.28, 0.2, 1.1]}>
        <circleGeometry args={[0.08, 24]} />
        <meshBasicMaterial color={color} transparent opacity={0.9} />
      </mesh>
      {/* Right iris ring */}
      <mesh ref={irisRightRef} position={[0.28, 0.2, 1.13]}>
        <ringGeometry args={[0.035, 0.055, 20]} />
        <meshBasicMaterial color={color} transparent opacity={0.35} />
      </mesh>
      {/* Right pupil */}
      <mesh ref={pupilRightRef} position={[0.28, 0.2, 1.18]}>
        <circleGeometry args={[0.03, 16]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.95} />
      </mesh>
      {/* Right pupil core */}
      <mesh position={[0.28, 0.2, 1.19]}>
        <circleGeometry args={[0.012, 12]} />
        <meshBasicMaterial color="#ffffff" />
      </mesh>

      {/* Left brow */}
      <group ref={leftBrowRef} position={[-0.28, 0.34, 1.1]}>
        <Line points={browPoints} color={color} lineWidth={1.2} transparent opacity={0.5} />
      </group>
      {/* Right brow */}
      <group ref={rightBrowRef} position={[0.28, 0.34, 1.1]}>
        <Line points={browPoints} color={color} lineWidth={1.2} transparent opacity={0.5} />
      </group>

      {/* Mouth line */}
      <group ref={mouthRef} position={[0, -0.25, 1.1]}>
        <Line points={mouthPoints} color={color} lineWidth={1.8} transparent opacity={0.7} />
      </group>
    </group>
  );
}

// ─── Inner glow sphere ──────────────────────────────────────────────────────

function InnerGlow({ emotion }: { emotion: string }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const glowColor = useRef(new THREE.Color(EMOTION_COLORS[emotion] || "var(--text-muted)"));

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    const t = clock.elapsedTime;
    const target = EMOTION_COLORS[emotion] || "var(--text-muted)";
    lerpColor(glowColor.current, target, 0.03);

    const mat = meshRef.current.material as THREE.MeshBasicMaterial;
    mat.color.copy(glowColor.current);
    mat.opacity = 0.12 + Math.sin(t * 1.5) * 0.04;

    // Subtle breathing scale
    const breathe = 1.0 + Math.sin(t * 0.8) * 0.02;
    meshRef.current.scale.setScalar(breathe);
  });

  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[0.7, 32, 32]} />
      <meshBasicMaterial color={EMOTION_COLORS[emotion]} transparent opacity={0.15} />
    </mesh>
  );
}

// ─── Main sphere mesh ───────────────────────────────────────────────────────

function AvatarMesh({ emotion, isSpeaking, audioLevel }: {
  emotion: string;
  isSpeaking: boolean;
  audioLevel: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const baseGeometry = useMemo(() => new THREE.SphereGeometry(1.2, 64, 64), []);
  const originalPositions = useMemo(
    () => new Float32Array(baseGeometry.attributes.position.array),
    [baseGeometry],
  );

  // Smooth color transition
  const meshColor = useRef(new THREE.Color(EMOTION_COLORS[emotion] || "var(--text-muted)"));
  const emissiveColor = useRef(new THREE.Color(EMOTION_COLORS[emotion] || "var(--text-muted)"));

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    const time = clock.elapsedTime;
    const speed = EMOTION_SPEEDS[emotion] || 0.3;
    const positions = meshRef.current.geometry.attributes.position;
    const target = EMOTION_COLORS[emotion] || "var(--text-muted)";

    // Smooth color transition
    lerpColor(meshColor.current, target, 0.03);
    lerpColor(emissiveColor.current, target, 0.03);

    const mat = meshRef.current.material as THREE.MeshStandardMaterial;
    mat.color.copy(meshColor.current);
    mat.emissive.copy(emissiveColor.current);

    const speakAmplitude = isSpeaking ? 0.03 + audioLevel * 0.25 : 0;

    for (let i = 0; i < positions.count; i++) {
      const ox = originalPositions[i * 3];
      const oy = originalPositions[i * 3 + 1];
      const oz = originalPositions[i * 3 + 2];

      const noiseVal =
        Math.sin(ox * 2 + time * speed) * 0.05 +
        Math.cos(oy * 2 + time * speed * 0.7) * 0.04 +
        Math.sin(oz * 1.5 + time * speed * 1.3) * 0.03 +
        speakAmplitude * Math.sin(ox * 5 + time * 3);

      const len = Math.sqrt(ox * ox + oy * oy + oz * oz);
      const nx = ox / len;
      const ny = oy / len;
      const nz = oz / len;

      positions.setXYZ(i, ox + nx * noiseVal, oy + ny * noiseVal, oz + nz * noiseVal);
    }
    positions.needsUpdate = true;

    // Gentle idle rotation
    meshRef.current.rotation.y += 0.001;
    meshRef.current.rotation.x = Math.sin(time * 0.15) * 0.03;

    // Opacity pulse when speaking
    if (isSpeaking) {
      mat.opacity = 0.35 + audioLevel * 0.2 + Math.sin(time * 4) * 0.05;
    } else {
      mat.opacity = 0.4;
    }
  });

  const color = EMOTION_COLORS[emotion] || EMOTION_COLORS.cold;

  return (
    <mesh ref={meshRef} geometry={baseGeometry}>
      <meshStandardMaterial
        color={color}
        transparent
        opacity={0.4}
        roughness={0.3}
        metalness={0.6}
        emissive={color}
        emissiveIntensity={0.3}
      />
    </mesh>
  );
}

// ─── Glow rings ─────────────────────────────────────────────────────────────

function GlowRing({ emotion, index = 0 }: { emotion: string; index?: number }) {
  const ringRef = useRef<THREE.Mesh>(null);
  const offset = index * Math.PI * 0.33;
  const ringColor = useRef(new THREE.Color(EMOTION_COLORS[emotion] || "var(--text-muted)"));

  useFrame(({ clock }) => {
    if (!ringRef.current) return;
    const t = clock.elapsedTime;
    ringRef.current.rotation.z = t * (0.08 + index * 0.04) + offset;
    ringRef.current.rotation.x = Math.sin(t * 0.3 + offset) * 0.15;

    lerpColor(ringColor.current, EMOTION_COLORS[emotion] || "var(--text-muted)", 0.03);
    const mat = ringRef.current.material as THREE.MeshBasicMaterial;
    mat.color.copy(ringColor.current);
    mat.opacity = 0.08 + Math.sin(t + offset) * 0.04;
  });

  const color = EMOTION_COLORS[emotion] || "var(--text-muted)";

  return (
    <mesh ref={ringRef} rotation={[Math.PI / 2 + offset * 0.2, 0, 0]}>
      <torusGeometry args={[2.0 + index * 0.5, 0.01, 16, 100]} />
      <meshBasicMaterial color={color} transparent opacity={0.1} />
    </mesh>
  );
}

// ─── Particle system ────────────────────────────────────────────────────────

function Particles({ emotion, count = 100 }: { emotion: string; count?: number }) {
  const pointsRef = useRef<THREE.Points>(null);
  const particleColor = useRef(new THREE.Color(EMOTION_COLORS[emotion] || "var(--text-muted)"));

  const [positions, vel, sizes] = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const vel = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 2.2 + Math.random() * 3.0;
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);
      vel[i * 3] = (Math.random() - 0.5) * 0.004;
      vel[i * 3 + 1] = (Math.random() - 0.5) * 0.004;
      vel[i * 3 + 2] = (Math.random() - 0.5) * 0.004;
      // Varied sizes for depth illusion
      sizes[i] = 0.015 + Math.random() * 0.035;
    }
    return [pos, vel, sizes];
  }, [count]);

  useFrame(({ clock }) => {
    if (!pointsRef.current) return;
    const t = clock.elapsedTime;
    const posAttr = pointsRef.current.geometry.attributes.position;

    lerpColor(particleColor.current, EMOTION_COLORS[emotion] || "var(--text-muted)", 0.03);
    (pointsRef.current.material as THREE.PointsMaterial).color.copy(particleColor.current);

    for (let i = 0; i < count; i++) {
      let x = posAttr.getX(i) + vel[i * 3];
      let y = posAttr.getY(i) + vel[i * 3 + 1];
      let z = posAttr.getZ(i) + vel[i * 3 + 2];

      x += Math.sin(t * 0.2 + i) * 0.002;
      y += Math.cos(t * 0.15 + i * 0.5) * 0.002;

      const dist = Math.sqrt(x * x + y * y + z * z);
      if (dist > 5.5 || dist < 1.8) {
        const nx = x / dist;
        const ny = y / dist;
        const nz = z / dist;
        const target = dist > 5.5 ? 4.5 : 2.2;
        x = nx * target;
        y = ny * target;
        z = nz * target;
      }

      posAttr.setXYZ(i, x, y, z);
    }
    posAttr.needsUpdate = true;

    // Pulsing size
    const mat = pointsRef.current.material as THREE.PointsMaterial;
    mat.size = 0.03 + Math.sin(t * 0.5) * 0.01;
  });

  const color = EMOTION_COLORS[emotion] || EMOTION_COLORS.cold;

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
          count={count}
        />
      </bufferGeometry>
      <pointsMaterial
        color={color}
        size={0.03}
        transparent
        opacity={0.6}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  );
}

// ─── Bloom post-processing ──────────────────────────────────────────────────

function BloomEffect() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [PostComponents, setPostComponents] = useState<{
    EffectComposer: React.ComponentType<any>;
    Bloom: React.ComponentType<any>;
  } | null>(null);

  useEffect(() => {
    import("@react-three/postprocessing").then((mod) => {
      setPostComponents({
        EffectComposer: mod.EffectComposer,
        Bloom: mod.Bloom,
      });
    }).catch(() => {
      // Postprocessing not available — skip bloom
    });
  }, []);

  if (!PostComponents) return null;

  const { EffectComposer, Bloom } = PostComponents;

  return (
    <EffectComposer>
      <Bloom
        luminanceThreshold={0.15}
        luminanceSmoothing={0.85}
        intensity={1.0}
        mipmapBlur
      />
    </EffectComposer>
  );
}

// ─── Responsive camera ──────────────────────────────────────────────────────

function ResponsiveCamera() {
  const { camera, size } = useThree();
  useEffect(() => {
    if (camera instanceof THREE.PerspectiveCamera) {
      camera.position.z = size.width < 400 ? 5.5 : 5;
      camera.updateProjectionMatrix();
    }
  }, [camera, size]);
  return null;
}

// ─── WebGL support check ────────────────────────────────────────────────────

function checkWebGLSupport(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

// ─── 2D SVG fallback ────────────────────────────────────────────────────────

function AvatarFallback({ emotion }: { emotion: string }) {
  const color = EMOTION_COLORS[emotion] || EMOTION_COLORS.cold;
  const label = EMOTION_MAP[emotion as EmotionState]?.labelRu || "НЕЙТРАЛЬНЫЙ";

  return (
    <div className="flex h-full w-full items-center justify-center">
      <div className="relative">
        <svg width="120" height="120" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r="55" fill="none" stroke={color} strokeWidth="1" opacity="0.3" />
          <circle cx="60" cy="60" r="45" fill="none" stroke={color} strokeWidth="0.5" opacity="0.2" />
          <circle cx="60" cy="60" r="35" fill={color} opacity="0.15" stroke={color} strokeWidth="1.5" />
          <circle cx="50" cy="55" r="4" fill={color} opacity="0.8" />
          <circle cx="70" cy="55" r="4" fill={color} opacity="0.8" />
          <path d="M48 70 Q60 76 72 70" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6" />
        </svg>
        <div
          className="absolute -bottom-6 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full px-3 py-1 font-mono text-xs uppercase tracking-wider"
          style={{
            background: "var(--glass-bg)",
            border: "1px solid var(--border-color)",
            color,
          }}
        >
          {label}
        </div>
      </div>
    </div>
  );
}

// ─── Main export ────────────────────────────────────────────────────────────

interface Avatar3DProps {
  emotion?: string;
  isSpeaking?: boolean;
  audioLevel?: number;
  className?: string;
}

export function Avatar3D({
  emotion = "cold",
  isSpeaking = false,
  audioLevel = 0,
  className = "",
}: Avatar3DProps) {
  const [webglSupported, setWebglSupported] = useState(true);
  const [contextLost, setContextLost] = useState(false);
  const reducedMotion = useReducedMotion();

  const checkGL = useCallback(() => {
    setWebglSupported(checkWebGLSupport());
  }, []);

  useEffect(() => {
    checkGL();
  }, [checkGL]);

  // Show lightweight SVG fallback for reduced motion, no WebGL, or context lost
  if (reducedMotion || !webglSupported || contextLost) {
    return (
      <div className={`relative ${className}`}>
        <AvatarFallback emotion={emotion} />
      </div>
    );
  }

  const color = EMOTION_COLORS[emotion] || EMOTION_COLORS.cold;

  return (
    <div className={`relative ${className}`}>
      <Canvas
        camera={{ position: [0, 0, 5], fov: 50 }}
        dpr={[1, 1.5]}
        style={{ background: "transparent" }}
        gl={{ antialias: true, alpha: true, powerPreference: "default" }}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.2;
          const canvas = gl.domElement;
          canvas.addEventListener("webglcontextlost", (e) => {
            e.preventDefault();
            setContextLost(true);
          });
        }}
      >
        <ResponsiveCamera />

        {/* Lighting */}
        <ambientLight intensity={0.3} />
        <pointLight position={[3, 3, 5]} intensity={0.4} color={color} />
        <pointLight position={[-3, -2, 3]} intensity={0.2} color="#ffffff" />

        {/* Jarvis-style AI projection */}
        <JarvisScene emotion={emotion} isSpeaking={isSpeaking} audioLevel={audioLevel} />

        {/* Bloom post-processing */}
        <BloomEffect />
      </Canvas>

      {/* Emotion label overlay */}
      <div
        className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-1 font-mono text-xs uppercase tracking-wider"
        style={{
          background: "var(--glass-bg)",
          border: "1px solid var(--border-color)",
          color,
        }}
      >
        {EMOTION_MAP[emotion as EmotionState]?.labelRu || "НЕЙТРАЛЬНЫЙ"}
      </div>
    </div>
  );
}
