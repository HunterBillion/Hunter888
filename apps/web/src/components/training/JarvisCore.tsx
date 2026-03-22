"use client";

/**
 * JarvisCore — Jarvis-style AI holographic projection.
 * Replaces the sphere avatar with a neural network visualization:
 * - Central glowing core (brain)
 * - Neural connection lines between nodes
 * - Orbiting data rings
 * - Pulse waves synchronized with emotion/audio
 * - Floating data particles
 */

import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { EMOTION_MAP, type EmotionState } from "@/types";

const EMOTION_COLORS: Record<string, string> = Object.fromEntries(
  Object.entries(EMOTION_MAP).map(([k, v]) => [k, v.color]),
);

// ── Neural Network Nodes ──────────────────────────────────

function NeuralNodes({ emotion, audioLevel }: { emotion: string; audioLevel: number }) {
  const groupRef = useRef<THREE.Group>(null);
  const color = EMOTION_COLORS[emotion] || "#8A2BE2";

  // Generate node positions in a spherical pattern
  const nodes = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    const phi = (1 + Math.sqrt(5)) / 2; // golden ratio
    for (let i = 0; i < 24; i++) {
      const y = 1 - (2 * i) / (24 - 1);
      const radius = Math.sqrt(1 - y * y);
      const theta = 2 * Math.PI * i / phi;
      pts.push(new THREE.Vector3(
        Math.cos(theta) * radius * 1.2,
        y * 1.2,
        Math.sin(theta) * radius * 1.2,
      ));
    }
    return pts;
  }, []);

  // Connection pairs (nearest neighbors)
  const connections = useMemo(() => {
    const pairs: [number, number][] = [];
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        if (nodes[i].distanceTo(nodes[j]) < 1.2) {
          pairs.push([i, j]);
        }
      }
    }
    return pairs;
  }, [nodes]);

  // Line geometry for connections
  const linePositions = useMemo(() => {
    const arr = new Float32Array(connections.length * 6);
    connections.forEach(([a, b], i) => {
      arr[i * 6] = nodes[a].x;
      arr[i * 6 + 1] = nodes[a].y;
      arr[i * 6 + 2] = nodes[a].z;
      arr[i * 6 + 3] = nodes[b].x;
      arr[i * 6 + 4] = nodes[b].y;
      arr[i * 6 + 5] = nodes[b].z;
    });
    return arr;
  }, [nodes, connections]);

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const t = clock.elapsedTime;
    // Slow rotation
    groupRef.current.rotation.y = t * 0.15;
    groupRef.current.rotation.x = Math.sin(t * 0.1) * 0.1;
    // Breathe scale with audio
    const breathe = 1 + Math.sin(t * 1.5) * 0.03 + audioLevel * 0.1;
    groupRef.current.scale.setScalar(breathe);
  });

  const nodeColor = useMemo(() => new THREE.Color(color), [color]);

  return (
    <group ref={groupRef}>
      {/* Neural nodes */}
      {nodes.map((pos, i) => (
        <mesh key={i} position={pos}>
          <sphereGeometry args={[0.04, 8, 8]} />
          <meshBasicMaterial color={nodeColor} transparent opacity={0.8} />
        </mesh>
      ))}

      {/* Connection lines */}
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[linePositions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={color} transparent opacity={0.2} />
      </lineSegments>
    </group>
  );
}

// ── Central Core ──────────────────────────────────────────

function Core({ emotion, isSpeaking, audioLevel }: { emotion: string; isSpeaking: boolean; audioLevel: number }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);
  const color = EMOTION_COLORS[emotion] || "#8A2BE2";
  const targetColor = useRef(new THREE.Color(color));

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    targetColor.current.lerp(new THREE.Color(color), 0.05);

    if (meshRef.current) {
      const mat = meshRef.current.material as THREE.MeshBasicMaterial;
      mat.color.copy(targetColor.current);
      // Pulse with speech
      const pulse = isSpeaking ? 0.4 + audioLevel * 0.3 : 0.3 + Math.sin(t * 2) * 0.05;
      meshRef.current.scale.setScalar(pulse);
    }

    if (glowRef.current) {
      const mat = glowRef.current.material as THREE.MeshBasicMaterial;
      mat.color.copy(targetColor.current);
      mat.opacity = isSpeaking ? 0.15 + audioLevel * 0.15 : 0.08 + Math.sin(t * 1.5) * 0.03;
      const glowScale = isSpeaking ? 1.5 + audioLevel * 0.8 : 1.2 + Math.sin(t * 1.5) * 0.2;
      glowRef.current.scale.setScalar(glowScale);
    }
  });

  return (
    <>
      {/* Inner core */}
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[1, 2]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={0.6} />
      </mesh>
      {/* Outer glow */}
      <mesh ref={glowRef}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.1} side={THREE.BackSide} />
      </mesh>
    </>
  );
}

// ── Data Rings ────────────────────────────────────────────

function DataRing({ emotion, radius, speed, tilt }: { emotion: string; radius: number; speed: number; tilt: number }) {
  const ref = useRef<THREE.Mesh>(null);
  const color = EMOTION_COLORS[emotion] || "#8A2BE2";

  useFrame(({ clock }) => {
    if (!ref.current) return;
    ref.current.rotation.z = clock.elapsedTime * speed;
  });

  return (
    <mesh ref={ref} rotation={[tilt, 0, 0]}>
      <torusGeometry args={[radius, 0.008, 8, 64]} />
      <meshBasicMaterial color={color} transparent opacity={0.25} />
    </mesh>
  );
}

// ── Pulse Wave ────────────────────────────────────────────

function PulseWaves({ emotion, isSpeaking }: { emotion: string; isSpeaking: boolean }) {
  const ref1 = useRef<THREE.Mesh>(null);
  const ref2 = useRef<THREE.Mesh>(null);
  const color = EMOTION_COLORS[emotion] || "#8A2BE2";

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const speed = isSpeaking ? 1.5 : 0.8;

    [ref1, ref2].forEach((ref, i) => {
      if (!ref.current) return;
      const phase = (t * speed + i * 1.5) % 3;
      const scale = 0.5 + phase * 0.8;
      const opacity = Math.max(0, 0.3 - phase * 0.1);
      ref.current.scale.setScalar(scale);
      (ref.current.material as THREE.MeshBasicMaterial).opacity = opacity;
    });
  });

  return (
    <>
      <mesh ref={ref1}>
        <ringGeometry args={[0.95, 1.0, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.2} side={THREE.DoubleSide} />
      </mesh>
      <mesh ref={ref2}>
        <ringGeometry args={[0.95, 1.0, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.15} side={THREE.DoubleSide} />
      </mesh>
    </>
  );
}

// ── Floating Data Particles ───────────────────────────────

function DataParticles({ emotion, count = 40 }: { emotion: string; count?: number }) {
  const ref = useRef<THREE.Points>(null);
  const color = EMOTION_COLORS[emotion] || "#8A2BE2";

  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 1.5 + Math.random() * 1.0;
      arr[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      arr[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      arr[i * 3 + 2] = r * Math.cos(phi);
    }
    return arr;
  }, [count]);

  useFrame(({ clock }) => {
    if (!ref.current) return;
    ref.current.rotation.y = clock.elapsedTime * 0.08;
    ref.current.rotation.x = Math.sin(clock.elapsedTime * 0.05) * 0.1;
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.04}
        color={color}
        transparent
        opacity={0.6}
        sizeAttenuation
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ── Main Export ────────────────────────────────────────────

interface JarvisCoreProps {
  emotion: string;
  isSpeaking: boolean;
  audioLevel: number;
}

export function JarvisScene({ emotion, isSpeaking, audioLevel }: JarvisCoreProps) {
  return (
    <>
      {/* Central AI brain */}
      <Core emotion={emotion} isSpeaking={isSpeaking} audioLevel={audioLevel} />

      {/* Neural network overlay */}
      <NeuralNodes emotion={emotion} audioLevel={audioLevel} />

      {/* Orbiting data rings */}
      <DataRing emotion={emotion} radius={1.8} speed={0.3} tilt={Math.PI * 0.1} />
      <DataRing emotion={emotion} radius={2.1} speed={-0.2} tilt={Math.PI * 0.35} />
      <DataRing emotion={emotion} radius={2.5} speed={0.15} tilt={Math.PI * 0.6} />

      {/* Expanding pulse waves */}
      <PulseWaves emotion={emotion} isSpeaking={isSpeaking} />

      {/* Orbiting data particles */}
      <DataParticles emotion={emotion} />
    </>
  );
}
