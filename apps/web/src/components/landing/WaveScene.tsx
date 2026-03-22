"use client";

import { useRef, useMemo, useEffect, useCallback, useState } from "react";
import { Canvas, useFrame, useThree, ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";

// ═══════════════════════════════════════════════════════════
//  Gerstner Wave Ocean — Dual-layer Points + mouse raycasting
// ═══════════════════════════════════════════════════════════

const vertexShader = /* glsl */ `
  uniform float uTime;
  uniform vec2 uMouse;
  uniform float uMouseActive;
  uniform float uClickRipple[15];
  uniform int uClickCount;
  uniform float uLayerOffset;
  uniform float uAmplitude;
  uniform float uTimeOffset;

  varying float vHeight;
  varying float vDepth;
  varying float vMouseDist;

  vec3 gerstner(vec2 p, float steep, float wl, vec2 dir, float spd, float t) {
    float k = 6.28318 / wl;
    float c = sqrt(9.81 / k);
    vec2 d = normalize(dir);
    float f = k * (dot(d, p) - c * spd * t);
    float a = steep / k;
    return vec3(d.x * a * cos(f), a * sin(f), d.y * a * cos(f));
  }

  void main() {
    vec3 pos = position;
    float t = uTime + uTimeOffset;
    float zRange = 60.0;
    vDepth = clamp((pos.z + zRange * 0.5) / zRange, 0.0, 1.0);

    vec3 wave = vec3(0.0);
    wave += gerstner(pos.xz, 0.12, 28.0, vec2(1.0, 0.3),  0.6, t);
    wave += gerstner(pos.xz, 0.08, 22.0, vec2(-0.5, 0.8), 0.5, t);
    wave += gerstner(pos.xz, 0.06, 12.0, vec2(0.7, -0.4), 1.0, t);
    wave += gerstner(pos.xz, 0.04, 8.0,  vec2(-0.3, 0.6), 1.3, t);
    wave += gerstner(pos.xz, 0.025, 5.0, vec2(0.9, 0.1),  1.6, t);
    wave += gerstner(pos.xz, 0.02, 3.5,  vec2(-0.6,-0.7), 2.0, t);

    float depthScale = 0.3 + vDepth * 0.7;
    wave *= depthScale * uAmplitude;
    pos += wave;
    pos.y += uLayerOffset;

    // Mouse
    float mouseDist = length(pos.xz - uMouse);
    float mR = 14.0;
    vMouseDist = mouseDist;

    if (uMouseActive > 0.01 && mouseDist < mR) {
      float f = 1.0 - mouseDist / mR;
      float s1 = f * f * (3.0 - 2.0 * f);
      float s2 = s1 * s1;
      pos.y -= s2 * 3.0 * uMouseActive;
      float rimC = mR * 0.72;
      float rimW = mR * 0.28;
      float rimD = abs(mouseDist - rimC);
      if (rimD < rimW) {
        float rF = 1.0 - rimD / rimW;
        pos.y += rF * rF * 1.8 * uMouseActive;
      }
      pos.y += sin(mouseDist * 0.7 - uTime * 4.5) * 0.4 * s1 * uMouseActive;
      pos.y += sin(mouseDist * 1.3 - uTime * 7.0) * 0.2 * s1 * s1 * uMouseActive;
      pos.y += sin(mouseDist * 2.2 - uTime * 10.0) * 0.08 * s2 * uMouseActive;
    }

    // Clicks
    for (int i = 0; i < 5; i++) {
      if (i >= uClickCount) break;
      float cx = uClickRipple[i * 3];
      float cz = uClickRipple[i * 3 + 1];
      float age = uClickRipple[i * 3 + 2];
      if (age > 4.0) continue;
      float cd = length(pos.xz - vec2(cx, cz));
      float wR = age * 20.0;
      float rW = 5.0 + age * 3.0;
      float rD = abs(cd - wR);
      if (rD < rW) {
        float rF = 1.0 - rD / rW;
        pos.y += rF * rF * 2.0 * exp(-age * 0.7) * sin(cd * 0.4 - age * 7.0);
      }
    }

    vHeight = pos.y - uLayerOffset;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
    float dist = length((modelViewMatrix * vec4(pos, 1.0)).xyz);
    gl_PointSize = max(1.0, (3.0 + vDepth * 5.0) * (80.0 / dist));
  }
`;

const fragmentShader = /* glsl */ `
  uniform vec3 uColorDeep;
  uniform vec3 uColorMid;
  uniform vec3 uColorCrest;
  uniform vec3 uColorFoam;
  uniform float uMouseActive;
  uniform float uAlphaBase;
  uniform float uAlphaDepthMul;

  varying float vHeight;
  varying float vDepth;
  varying float vMouseDist;

  void main() {
    vec2 c = gl_PointCoord - 0.5;
    float d = length(c);
    if (d > 0.5) discard;
    float alpha = smoothstep(0.5, 0.15, d);

    float h = clamp((vHeight + 2.0) / 4.0, 0.0, 1.0);
    vec3 color = mix(uColorDeep, uColorMid, smoothstep(0.0, 0.35, h));
    color = mix(color, uColorCrest, smoothstep(0.35, 0.65, h));
    color = mix(color, uColorFoam, smoothstep(0.65, 1.0, h));

    alpha *= uAlphaBase + vDepth * uAlphaDepthMul;
    alpha *= smoothstep(0.0, 0.12, vDepth);

    // Mouse glow
    float mR = 14.0;
    if (uMouseActive > 0.01 && vMouseDist < mR) {
      float f = 1.0 - vMouseDist / mR;
      float s = f * f * (3.0 - 2.0 * f);
      float rimD = abs(vMouseDist - mR * 0.72);
      if (rimD < mR * 0.28) {
        float rF = 1.0 - rimD / (mR * 0.28);
        color = mix(color, uColorFoam, rF * rF * 0.7 * uMouseActive);
        alpha = min(1.0, alpha + rF * 0.4 * uMouseActive);
      }
      color *= 1.0 - s * 0.25 * uMouseActive;
      alpha = min(1.0, alpha + s * 0.2 * uMouseActive);
    }

    if (h > 0.55) alpha = min(1.0, alpha + (h - 0.55) * 0.5);
    gl_FragColor = vec4(color, alpha);
  }
`;

// ── Ocean Layer ────────────────────────────────────────────
interface LayerCfg {
  layerOffset: number;
  amplitude: number;
  timeOffset: number;
  alphaBase: number;
  alphaDepthMul: number;
  cols: number;
  rows: number;
  xSpan: number;
  zSpan: number;
  colorsDark: { deep: number; mid: number; crest: number; foam: number };
  colorsLight: { deep: number; mid: number; crest: number; foam: number };
}

function OceanLayer({
  cfg, isDark, mouseSmooth, mouseActive, clicksRef,
}: {
  cfg: LayerCfg;
  isDark: boolean;
  mouseSmooth: React.MutableRefObject<THREE.Vector2>;
  mouseActive: React.MutableRefObject<number>;
  clicksRef: React.MutableRefObject<{ x: number; z: number; age: number }[]>;
}) {
  const meshRef = useRef<THREE.Points>(null);

  const positions = useMemo(() => {
    const pos = new Float32Array(cfg.cols * cfg.rows * 3);
    let idx = 0;
    for (let r = 0; r < cfg.rows; r++) {
      for (let c = 0; c < cfg.cols; c++) {
        pos[idx++] = (c / (cfg.cols - 1) - 0.5) * cfg.xSpan;
        pos[idx++] = 0;
        pos[idx++] = (r / (cfg.rows - 1) - 0.5) * cfg.zSpan;
      }
    }
    return pos;
  }, [cfg.cols, cfg.rows, cfg.xSpan, cfg.zSpan]);

  const pal = isDark ? cfg.colorsDark : cfg.colorsLight;
  const colors = useMemo(() => ({
    deep:  new THREE.Color(pal.deep),
    mid:   new THREE.Color(pal.mid),
    crest: new THREE.Color(pal.crest),
    foam:  new THREE.Color(pal.foam),
  }), [pal.deep, pal.mid, pal.crest, pal.foam]);

  const uniforms = useMemo(() => ({
    uTime: { value: 0 },
    uMouse: { value: new THREE.Vector2(-999, -999) },
    uMouseActive: { value: 0 },
    uClickRipple: { value: new Float32Array(15) },
    uClickCount: { value: 0 },
    uLayerOffset: { value: cfg.layerOffset },
    uAmplitude: { value: cfg.amplitude },
    uTimeOffset: { value: cfg.timeOffset },
    uAlphaBase: { value: cfg.alphaBase },
    uAlphaDepthMul: { value: cfg.alphaDepthMul },
    uColorDeep: { value: colors.deep.clone() },
    uColorMid: { value: colors.mid.clone() },
    uColorCrest: { value: colors.crest.clone() },
    uColorFoam: { value: colors.foam.clone() },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), []);

  useEffect(() => {
    uniforms.uColorDeep.value.copy(colors.deep);
    uniforms.uColorMid.value.copy(colors.mid);
    uniforms.uColorCrest.value.copy(colors.crest);
    uniforms.uColorFoam.value.copy(colors.foam);
  }, [colors, uniforms]);

  useFrame((_, delta) => {
    if (!meshRef.current) return;
    const m = meshRef.current.material as THREE.ShaderMaterial;
    m.uniforms.uTime.value += delta;
    m.uniforms.uMouse.value.copy(mouseSmooth.current);
    m.uniforms.uMouseActive.value = mouseActive.current;
    const rd = m.uniforms.uClickRipple.value as Float32Array;
    clicksRef.current.forEach((c, i) => {
      rd[i * 3] = c.x; rd[i * 3 + 1] = c.z; rd[i * 3 + 2] = c.age;
    });
    m.uniforms.uClickCount.value = clicksRef.current.length;
  });

  return (
    <points ref={meshRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ── Mouse Catcher ──────────────────────────────────────────
function MouseCatcher({
  mouseWorld, clicksRef,
}: {
  mouseWorld: React.MutableRefObject<THREE.Vector2>;
  clicksRef: React.MutableRefObject<{ x: number; z: number; age: number }[]>;
}) {
  const { camera } = useThree();
  const rc = useRef(new THREE.Raycaster());
  const pl = useRef(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0));

  const project = useCallback((e: ThreeEvent<PointerEvent>) => {
    rc.current.setFromCamera(e.pointer, camera);
    const hit = new THREE.Vector3();
    if (rc.current.ray.intersectPlane(pl.current, hit)) {
      mouseWorld.current.set(hit.x, hit.z);
    }
  }, [camera, mouseWorld]);

  const click = useCallback((e: ThreeEvent<MouseEvent>) => {
    rc.current.setFromCamera(e.pointer, camera);
    const hit = new THREE.Vector3();
    if (rc.current.ray.intersectPlane(pl.current, hit)) {
      clicksRef.current.push({ x: hit.x, z: hit.z, age: 0 });
      if (clicksRef.current.length > 5) clicksRef.current.shift();
    }
  }, [camera, clicksRef]);

  return (
    <mesh
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, 0, 0]}
      onPointerMove={project}
      onPointerLeave={() => mouseWorld.current.set(-999, -999)}
      onClick={click}
    >
      <planeGeometry args={[200, 200]} />
      <meshBasicMaterial transparent opacity={0} depthWrite={false} colorWrite={false} side={THREE.DoubleSide} />
    </mesh>
  );
}

// ── Shared State ───────────────────────────────────────────
function Tick({
  mouseWorld, mouseSmooth, mouseActive, clicksRef,
}: {
  mouseWorld: React.MutableRefObject<THREE.Vector2>;
  mouseSmooth: React.MutableRefObject<THREE.Vector2>;
  mouseActive: React.MutableRefObject<number>;
  clicksRef: React.MutableRefObject<{ x: number; z: number; age: number }[]>;
}) {
  useFrame((_, dt) => {
    const isActive = mouseWorld.current.x > -500;
    // Snap instantly when mouse enters (coming from -999), then smooth-track
    const dist = mouseSmooth.current.distanceTo(mouseWorld.current);
    const lerpFactor = dist > 50 ? 1.0 : 0.18;
    mouseSmooth.current.lerp(mouseWorld.current, lerpFactor);
    const tgt = isActive ? 1 : 0;
    mouseActive.current += (tgt - mouseActive.current) * 0.12;
    for (const c of clicksRef.current) c.age += dt;
    clicksRef.current = clicksRef.current.filter(c => c.age < 4);
  });
  return null;
}

// ── Layer configs ──────────────────────────────────────────
const LAYER_MAIN: LayerCfg = {
  layerOffset: 0,
  amplitude: 1.0,
  timeOffset: 0,
  alphaBase: 0.18,
  alphaDepthMul: 0.55,
  cols: 220,
  rows: 80,
  xSpan: 85,
  zSpan: 65,
  colorsDark:  { deep: 0x0c0423, mid: 0x501c9b, crest: 0x8a2be2, foam: 0xd282ff },
  colorsLight: { deep: 0x7b68ae, mid: 0x8b6cc2, crest: 0x905ced, foam: 0xc4a8f0 },
};

const LAYER_SUB: LayerCfg = {
  layerOffset: -1.8,
  amplitude: 0.35,
  timeOffset: 5.0,
  alphaBase: 0.05,
  alphaDepthMul: 0.25,
  cols: 100,
  rows: 35,
  xSpan: 70,
  zSpan: 45,
  colorsDark:  { deep: 0x080318, mid: 0x2e0f6b, crest: 0x6a1fb0, foam: 0x9b5cd6 },
  colorsLight: { deep: 0x9080b8, mid: 0xa090d0, crest: 0x7b5cb0, foam: 0xb8a0d8 },
};

// ── Floating Particles ─────────────────────────────────────
function FloatingParticles({ isDark }: { isDark: boolean }) {
  const count = 60;
  const ref = useRef<THREE.Points>(null);

  const [positions, speeds] = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const spd = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 80;
      pos[i * 3 + 1] = Math.random() * 25 - 5;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 60;
      spd[i] = 0.3 + Math.random() * 0.8;
    }
    return [pos, spd];
  }, []);

  useFrame(() => {
    if (!ref.current) return;
    const posArr = ref.current.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < count; i++) {
      posArr[i * 3 + 1] += speeds[i] * 0.015;
      // Reset when above view
      if (posArr[i * 3 + 1] > 25) {
        posArr[i * 3 + 1] = -5;
        posArr[i * 3] = (Math.random() - 0.5) * 80;
        posArr[i * 3 + 2] = (Math.random() - 0.5) * 60;
      }
    }
    ref.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.15}
        color={isDark ? "#8B5CF6" : "#7C3AED"}
        transparent
        opacity={0.5}
        sizeAttenuation
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ── Main Export ────────────────────────────────────────────
export function WaveScene() {
  const [isDark, setIsDark] = useState(true);
  const mouseWorld = useRef(new THREE.Vector2(-999, -999));
  const mouseSmooth = useRef(new THREE.Vector2(-999, -999));
  const mouseActive = useRef(0);
  const clicksRef = useRef<{ x: number; z: number; age: number }[]>([]);

  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  const shared = { mouseSmooth, mouseActive, clicksRef };

  return (
    <Canvas
      camera={{ position: [0, 18, 30], fov: 55, near: 0.1, far: 200 }}
      style={{ position: "absolute", inset: 0 }}
      gl={{ antialias: false, alpha: true, powerPreference: "high-performance" }}
      dpr={[1, 1.5]}
      eventPrefix="client"
    >
      <Tick mouseWorld={mouseWorld} {...shared} />
      <OceanLayer cfg={LAYER_SUB} isDark={isDark} {...shared} />
      <OceanLayer cfg={LAYER_MAIN} isDark={isDark} {...shared} />
      <MouseCatcher mouseWorld={mouseWorld} clicksRef={clicksRef} />
      <FloatingParticles isDark={isDark} />
    </Canvas>
  );
}
