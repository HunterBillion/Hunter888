"use client";

import { useRef, useMemo, useEffect, useCallback, useState } from "react";
import { Canvas, useFrame, useThree, ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { ShaderPass } from "three/examples/jsm/postprocessing/ShaderPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";

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
  varying float vEdgeFade;

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
    float zRange = 100.0;
    vDepth = clamp((pos.z + zRange * 0.5) / zRange, 0.0, 1.0);

    vec3 wave = vec3(0.0);
    wave += gerstner(pos.xz, 0.14, 28.0, vec2(1.0, 0.3),  0.75, t);
    wave += gerstner(pos.xz, 0.10, 22.0, vec2(-0.5, 0.8), 0.65, t);
    wave += gerstner(pos.xz, 0.07, 12.0, vec2(0.7, -0.4), 1.25, t);
    wave += gerstner(pos.xz, 0.05, 8.0,  vec2(-0.3, 0.6), 1.6, t);
    wave += gerstner(pos.xz, 0.03, 5.0,  vec2(0.9, 0.1),  2.0, t);
    wave += gerstner(pos.xz, 0.025, 3.5, vec2(-0.6,-0.7), 2.5, t);
    wave += gerstner(pos.xz, 0.015, 2.0, vec2(0.4, 0.9),  3.0, t);
    wave += gerstner(pos.xz, 0.015, 2.0, vec2(-0.8, 0.3), 3.2, t);

    float depthScale = 0.3 + vDepth * 0.7;
    wave *= depthScale * uAmplitude;
    pos += wave;
    pos.y += uLayerOffset;

    // World-space XZ — учитываем OceanDrift (parent group сдвигается по X),
    // иначе uMouse (world) не совпадает с pos.xz (local) и курсор отстаёт
    // на величину drift.position.x. Раньше это давало "shadow 4-5 см справа".
    vec2 worldXZ = (modelMatrix * vec4(pos, 1.0)).xz;

    // Mouse
    float mouseDist = length(worldXZ - uMouse);
    float mR = 18.0;
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
      pos.y += sin(mouseDist * 3.5 - uTime * 14.0) * 0.04 * s2 * uMouseActive;
    }

    // Clicks
    for (int i = 0; i < 5; i++) {
      if (i >= uClickCount) break;
      float cx = uClickRipple[i * 3];
      float cz = uClickRipple[i * 3 + 1];
      float age = uClickRipple[i * 3 + 2];
      if (age > 4.0) continue;
      float cd = length(worldXZ - vec2(cx, cz));
      float wR = age * 20.0;
      float rW = 5.0 + age * 3.0;
      float rD = abs(cd - wR);
      if (rD < rW) {
        float rF = 1.0 - rD / rW;
        pos.y += rF * rF * 2.0 * exp(-age * 0.7) * sin(cd * 0.4 - age * 7.0);
      }
    }

    vHeight = pos.y - uLayerOffset;
    // Soft edge fade — points near boundaries fade out smoothly
    float xEdge = 1.0 - smoothstep(0.93, 1.0, abs(position.x) / (uAmplitude > 0.5 ? 85.0 : 75.0));
    float zEdge = 1.0 - smoothstep(0.90, 1.0, abs(position.z) / (uAmplitude > 0.5 ? 85.0 : 75.0));
    vEdgeFade = xEdge * zEdge;
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
  varying float vEdgeFade;

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
    float mR = 18.0;
    if (uMouseActive > 0.01 && vMouseDist < mR) {
      float f = 1.0 - vMouseDist / mR;
      float s = f * f * (3.0 - 2.0 * f);
      float rimD = abs(vMouseDist - mR * 0.72);
      if (rimD < mR * 0.28) {
        float rF = 1.0 - rimD / (mR * 0.28);
        color = mix(color, uColorFoam * 1.3, rF * rF * 0.85 * uMouseActive);
        alpha = min(1.0, alpha + rF * 0.55 * uMouseActive);
      }
      color *= 1.0 - s * 0.15 * uMouseActive;
      alpha = min(1.0, alpha + s * 0.3 * uMouseActive);
    }

    if (h > 0.55) alpha = min(1.0, alpha + (h - 0.55) * 0.5);
    alpha *= vEdgeFade;
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
  // eslint-disable-next-line react-hooks/exhaustive-deps -- uniforms created once, updated via useFrame (not deps)
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
      // 2026-04-18: onPointerEnter отдельно проецирует первую позицию —
      // иначе Tick дожидается первого onPointerMove, и юзер видит пустой
      // кадр перед "выстрелом" волны. Теперь волна живёт от первого пикселя.
      onPointerEnter={project}
      onPointerMove={project}
      onPointerLeave={() => mouseWorld.current.set(-999, -999)}
      onClick={click}
    >
      <planeGeometry args={[300, 300]} />
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
  // Track previous active state to detect "just entered" transitions so we
  // can snap instantly on first entry (instead of the user moving and seeing
  // no compression until the 2nd frame due to lerp lag).
  const wasActive = useRef(false);

  useFrame((_, dt) => {
    const isActive = mouseWorld.current.x > -500;

    // 2026-04-18 fix: "волна появляется со второго раза" — при первом
    // pointer-enter устанавливаем mouseSmooth = mouseWorld без lerp и
    // mouseActive = 1 сразу. Далее — обычный smooth-track.
    const justEntered = isActive && !wasActive.current;
    if (justEntered) {
      mouseSmooth.current.copy(mouseWorld.current);
      mouseActive.current = 1.0;
    } else {
      // Фактор lerp увеличен 0.18 → 0.28 (быстрее следует за курсором,
      // меньше "shadow 4-5cm behind the cursor").
      const dist = mouseSmooth.current.distanceTo(mouseWorld.current);
      const lerpFactor = dist > 50 ? 1.0 : 0.28;
      mouseSmooth.current.lerp(mouseWorld.current, lerpFactor);
      const tgt = isActive ? 1 : 0;
      // Также быстрее гасим/разгоняем активность: 0.12 → 0.22
      mouseActive.current += (tgt - mouseActive.current) * 0.22;
    }

    wasActive.current = isActive;

    for (const c of clicksRef.current) c.age += dt;
    clicksRef.current = clicksRef.current.filter(c => c.age < 4);
  });
  return null;
}

// ── Adaptive quality ──────────────────────────────────────
// Detect low-power devices: mobile, low-res screens, or touch-primary devices
function getQualityScale(): number {
  if (typeof window === "undefined") return 1;
  const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  const isTouch = "ontouchstart" in window || navigator.maxTouchPoints > 0;
  const isLowRes = window.devicePixelRatio <= 1;
  const isSmall = window.innerWidth < 768;
  if (isMobile || (isTouch && isSmall)) return 0.4;  // ~15K → ~6K points
  if (isLowRes || isSmall) return 0.6;                // ~15K → ~9K points
  return 1;
}

// ── Layer configs ──────────────────────────────────────────
function getLayerConfigs(): { main: LayerCfg; sub: LayerCfg } {
  const q = getQualityScale();
  return {
    main: {
      layerOffset: 0,
      amplitude: 1.0,
      timeOffset: 0,
      alphaBase: 0.24,
      alphaDepthMul: 0.60,
      cols: Math.round(400 * q),
      rows: Math.round(130 * q),
      xSpan: 160,
      zSpan: 160,
      colorsDark:  { deep: 0x1a0840, mid: 0x6b2dc4, crest: 0x9a3bef, foam: 0xd282ff },
      colorsLight: { deep: 0x7b68ae, mid: 0x8b6cc2, crest: 0x905ced, foam: 0xc4a8f0 },
    },
    sub: {
      layerOffset: -1.8,
      amplitude: 0.35,
      timeOffset: 5.0,
      alphaBase: 0.05,
      alphaDepthMul: 0.25,
      cols: Math.round(200 * q),
      rows: Math.round(65 * q),
      xSpan: 140,
      zSpan: 80,
      colorsDark:  { deep: 0x10052a, mid: 0x3a1580, crest: 0x7a2bc8, foam: 0xab6ce0 },
      colorsLight: { deep: 0x9080b8, mid: 0xa090d0, crest: 0x7b5cb0, foam: 0xb8a0d8 },
    },
  };
}

// ── Floating Particles ─────────────────────────────────────
function FloatingParticles({ isDark }: { isDark: boolean }) {
  const count = 80;
  const ref = useRef<THREE.Points>(null);

  const [positions, speeds] = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const spd = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 150;
      pos[i * 3 + 1] = Math.random() * 25 - 5;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 140;
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
        posArr[i * 3] = (Math.random() - 0.5) * 150;
        posArr[i * 3 + 2] = (Math.random() - 0.5) * 140;
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
        color={isDark ? "#6B4DC7" : "#5A3DB5"}
        transparent
        opacity={0.5}
        sizeAttenuation
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ── Pixel Post-Processing ─────────────────────────────────
// Combined pixelation + color quantization in a single pass (lightweight)
const pixelQuantizeShaderDef = {
  uniforms: {
    tDiffuse: { value: null },
    resolution: { value: new THREE.Vector2(1, 1) },
    pixelSize: { value: 6.0 },
    levels: { value: 8.0 },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
  `,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    uniform vec2 resolution;
    uniform float pixelSize;
    uniform float levels;
    varying vec2 vUv;
    void main() {
      vec2 dxy = pixelSize / resolution;
      vec2 coord = dxy * floor(vUv / dxy + 0.5);
      vec4 c = texture2D(tDiffuse, coord);
      c.rgb = floor(c.rgb * levels + 0.5) / levels;
      gl_FragColor = c;
    }
  `,
};

function PixelPostProcessing() {
  const { gl, scene, camera, size } = useThree();

  const composer = useMemo(() => {
    const c = new EffectComposer(gl);
    c.addPass(new RenderPass(scene, camera));
    c.addPass(new ShaderPass(pixelQuantizeShaderDef));
    c.addPass(new OutputPass());
    return c;
  }, [gl, scene, camera]);

  useEffect(() => {
    composer.setSize(size.width, size.height);
    for (const pass of composer.passes) {
      if ((pass as ShaderPass).uniforms?.resolution) {
        (pass as ShaderPass).uniforms.resolution.value.set(size.width, size.height);
      }
    }
  }, [composer, size]);

  useFrame(() => {
    composer.render();
  }, 1);

  return null;
}

// ── Pixel Splash Overlay (2D Canvas) ──────────────────────
const SPLASH_COLORS = ["#d282ff", "#9a3bef", "#6b2dc4", "#FFD700"];

interface SplashParticle {
  x: number; y: number; vx: number; vy: number;
  color: string; size: number; life: number;
}

function PixelSplash() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<SplashParticle[]>([]);

  // Resize + click + animation — all in one effect using parent element
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const parent = canvas.parentElement;
    if (!parent) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Sync size
    const sync = () => { canvas.width = parent.clientWidth; canvas.height = parent.clientHeight; };
    sync();
    window.addEventListener("resize", sync);

    // Click → spawn particles
    const handleClick = (e: MouseEvent) => {
      const rect = parent.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      for (let i = 0; i < 40; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = 1.5 + Math.random() * 4;
        particlesRef.current.push({
          x, y,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed - 2,
          color: SPLASH_COLORS[Math.floor(Math.random() * SPLASH_COLORS.length)],
          size: Math.random() > 0.6 ? 8 : 5,
          life: 1,
        });
      }
    };
    parent.addEventListener("click", handleClick);

    // Animate
    let raf: number;
    const animate = () => {
      const particles = particlesRef.current;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.12;
        p.life -= 0.015;
        if (p.life <= 0) { particles.splice(i, 1); continue; }
        ctx.globalAlpha = p.life;
        ctx.fillStyle = p.color;
        ctx.fillRect(Math.floor(p.x), Math.floor(p.y), p.size, p.size);
      }
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(animate);
    };
    raf = requestAnimationFrame(animate);

    return () => {
      window.removeEventListener("resize", sync);
      parent.removeEventListener("click", handleClick);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1 }}
    />
  );
}

// ── Ocean Drift — subtle horizontal movement ──────────────
function OceanDrift({ children }: { children: React.ReactNode }) {
  const groupRef = useRef<THREE.Group>(null);
  useFrame((_, dt) => {
    if (!groupRef.current) return;
    groupRef.current.position.x += 0.5 * dt;
    // Wrap to avoid float precision loss over time
    if (groupRef.current.position.x > 40) groupRef.current.position.x -= 80;
  });
  return <group ref={groupRef}>{children}</group>;
}

// ── Main Export ────────────────────────────────────────────
export function WaveScene() {
  const [isDark, setIsDark] = useState(true);
  const [contextLost, setContextLost] = useState(false);
  const mouseWorld = useRef(new THREE.Vector2(-999, -999));
  const mouseSmooth = useRef(new THREE.Vector2(-999, -999));
  const mouseActive = useRef(0);
  const clicksRef = useRef<{ x: number; z: number; age: number }[]>([]);

  // Compute layer configs once on mount (adapts to device capability)
  const layers = useMemo(() => getLayerConfigs(), []);

  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  const shared = { mouseSmooth, mouseActive, clicksRef };

  // Graceful fallback when WebGL context is lost
  if (contextLost) {
    return (
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(ellipse 70% 50% at 50% 80%, var(--grid-glow) 0%, transparent 70%)",
          opacity: 0.4,
        }}
      />
    );
  }

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <Canvas
        camera={{ position: [0, 16, 42], fov: 60, near: 0.1, far: 300 }}
        style={{ position: "absolute", inset: 0 }}
        gl={{ antialias: false, alpha: true, powerPreference: "high-performance" }}
        dpr={[1, 1.5]}
        eventPrefix="client"
        onCreated={({ gl }) => {
          gl.domElement.addEventListener("webglcontextlost", (e) => {
            e.preventDefault();
            setContextLost(true);
          });
          // User-first Bug 3 (2026-04-29): listen for restoration too.
          // Pre-fix the contextLost state was a one-way trip: once the
          // GPU reclaimed the context (page navigation, tab visibility,
          // power saving), WaveScene stayed as the fallback gradient
          // forever even when the user returned. With a restored handler
          // R3F is told to re-init the scene the next render tick.
          gl.domElement.addEventListener("webglcontextrestored", () => {
            setContextLost(false);
          });
        }}
      >
        <fog attach="fog" args={[isDark ? "#100F1A" : "#E8E4F0", 80, 160]} />
        <Tick mouseWorld={mouseWorld} {...shared} />
        <OceanDrift>
          <OceanLayer cfg={layers.sub} isDark={isDark} {...shared} />
          <OceanLayer cfg={layers.main} isDark={isDark} {...shared} />
        </OceanDrift>
        <MouseCatcher mouseWorld={mouseWorld} clicksRef={clicksRef} />
        <FloatingParticles isDark={isDark} />
        <PixelPostProcessing />
      </Canvas>
      <PixelSplash key="splash" />
    </div>
  );
}
