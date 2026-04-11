"use client";

/**
 * VRM Avatar — Phase 2 replacement for Avatar3D.
 *
 * Uses @pixiv/three-vrm to load .vrm models with:
 * - Emotion-driven blend shape expressions
 * - Audio-level lip sync (frequency band analysis)
 * - Idle animations (blink, breathing, head sway)
 * - LookAt camera tracking
 *
 * Falls back to Avatar3D if VRM model not available or WebGL unsupported.
 *
 * Requires: npm install @pixiv/three-vrm
 * Models: placed in public/models/*.vrm
 */

import { useRef, useEffect, useState, useCallback, useMemo } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

// ── Emotion → VRM BlendShape mapping ──────────────────────────────────────────
// VRM standard expression names: happy, angry, sad, relaxed, surprised, neutral
const EMOTION_BLENDSHAPES: Record<string, Record<string, number>> = {
  cold:        { neutral: 0.7, angry: 0.2 },
  hostile:     { angry: 0.9 },
  hangup:      { angry: 0.5, sad: 0.3 },
  guarded:     { neutral: 0.6, angry: 0.1 },
  testing:     { neutral: 0.5, surprised: 0.2 },
  curious:     { neutral: 0.3, surprised: 0.4 },
  callback:    { neutral: 0.5, relaxed: 0.2 },
  considering: { neutral: 0.4, relaxed: 0.3 },
  negotiating: { neutral: 0.2, happy: 0.3, relaxed: 0.2 },
  deal:        { happy: 0.7, relaxed: 0.3 },
  // Legacy aliases
  skeptical:   { neutral: 0.6, angry: 0.1 },
  warming:     { neutral: 0.3, surprised: 0.3 },
  open:        { neutral: 0.3, happy: 0.2, relaxed: 0.2 },
};

const ALL_EXPRESSIONS = ["neutral", "happy", "angry", "sad", "relaxed", "surprised"];
const LERP_SPEED = 0.04;

// ── VRM Model Loader + Animator ───────────────────────────────────────────────

function VRMScene({
  modelUrl,
  emotion,
  audioLevel,
  isSpeaking,
}: {
  modelUrl: string;
  emotion: string;
  audioLevel: number;
  isSpeaking: boolean;
}) {
  const vrmRef = useRef<any>(null);
  const { scene, camera } = useThree();
  const [loaded, setLoaded] = useState(false);

  // Load VRM model
  useEffect(() => {
    let disposed = false;

    async function loadVRM() {
      try {
        // Dynamic import — @pixiv/three-vrm is optional dependency
        const { GLTFLoader } = await import("three/examples/jsm/loaders/GLTFLoader.js");
        // @ts-ignore — package may not be installed yet (optional)
        const { VRMLoaderPlugin, VRMUtils } = await import("@pixiv/three-vrm");

        const loader = new GLTFLoader();
        loader.register((parser: any) => new VRMLoaderPlugin(parser));

        loader.load(
          modelUrl,
          (gltf: any) => {
            if (disposed) return;
            const vrm = gltf.userData.vrm;
            if (!vrm) return;

            VRMUtils.removeUnnecessaryVertices(gltf.scene);
            VRMUtils.removeUnnecessaryJoints(gltf.scene);
            VRMUtils.rotateVRM0(vrm);

            scene.add(vrm.scene);
            vrmRef.current = vrm;
            setLoaded(true);
          },
          undefined,
          (err: any) => {
            console.warn("[VRMAvatar] Failed to load model:", err);
          },
        );
      } catch (err) {
        console.warn("[VRMAvatar] @pixiv/three-vrm not installed or model load failed:", err);
      }
    }

    loadVRM();

    return () => {
      disposed = true;
      if (vrmRef.current) {
        scene.remove(vrmRef.current.scene);
        vrmRef.current = null;
      }
    };
  }, [modelUrl, scene]);

  // Animation loop
  useFrame((state, delta) => {
    const vrm = vrmRef.current;
    if (!vrm) return;

    const t = state.clock.elapsedTime;
    const expr = vrm.expressionManager;

    // 1. Emotion blendshapes (smooth lerp)
    if (expr) {
      const targets = EMOTION_BLENDSHAPES[emotion] || EMOTION_BLENDSHAPES.cold;
      for (const name of ALL_EXPRESSIONS) {
        const target = targets[name] || 0;
        const current = expr.getValue(name) ?? 0;
        expr.setValue(name, THREE.MathUtils.lerp(current, target, LERP_SPEED));
      }
    }

    // 2. Lip sync from audioLevel
    if (expr) {
      if (isSpeaking && audioLevel > 0.01) {
        const mouthOpen = audioLevel * 0.7;
        const mouthRound = audioLevel * 0.3 * Math.sin(t * 6);
        expr.setValue("aa", THREE.MathUtils.lerp(expr.getValue("aa") ?? 0, mouthOpen, 0.15));
        expr.setValue("oh", THREE.MathUtils.lerp(expr.getValue("oh") ?? 0, Math.max(0, mouthRound), 0.1));
      } else {
        expr.setValue("aa", THREE.MathUtils.lerp(expr.getValue("aa") ?? 0, 0, 0.1));
        expr.setValue("oh", THREE.MathUtils.lerp(expr.getValue("oh") ?? 0, 0, 0.1));
      }
    }

    // 3. Idle blink (every 4-6 seconds)
    if (expr) {
      const blinkCycle = Math.sin(t * 0.8) * Math.sin(t * 1.3);
      expr.setValue("blink", blinkCycle > 0.95 ? 1 : 0);
    }

    // 4. LookAt camera
    if (vrm.lookAt) {
      vrm.lookAt.target = camera;
    }

    // 5. Subtle head sway (idle animation)
    if (vrm.humanoid) {
      const head = vrm.humanoid.getNormalizedBoneNode("head");
      if (head) {
        head.rotation.y = Math.sin(t * 0.3) * 0.03;
        head.rotation.x = Math.sin(t * 0.2) * 0.02;
      }
    }

    vrm.update(delta);
  });

  return null; // VRM adds itself to scene via scene.add()
}

// ── Main Export ───────────────────────────────────────────────────────────────

interface VRMAvatarProps {
  emotion?: string;
  isSpeaking?: boolean;
  audioLevel?: number;
  className?: string;
  modelUrl?: string;
}

export function VRMAvatar({
  emotion = "cold",
  isSpeaking = false,
  audioLevel = 0,
  className = "",
  modelUrl = "/models/client_default.vrm",
}: VRMAvatarProps) {
  const [webglSupported, setWebglSupported] = useState(true);
  const [vrmAvailable, setVrmAvailable] = useState(true);
  const [contextLost, setContextLost] = useState(false);

  useEffect(() => {
    // Check WebGL
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
    if (!gl) {
      setWebglSupported(false);
      return;
    }
    // Check if @pixiv/three-vrm is installed
    // @ts-ignore — optional dependency
    import("@pixiv/three-vrm")
      .then(() => setVrmAvailable(true))
      .catch(() => setVrmAvailable(false));
  }, []);

  // Fallback to Avatar3D if VRM not available
  if (!webglSupported || !vrmAvailable || contextLost) {
    return null; // Parent will use Avatar3D fallback
  }

  return (
    <div className={className}>
      <Canvas
        camera={{ position: [0, 1.3, 2.0], fov: 25 }}
        dpr={[1, 1.5]}
        style={{ background: "transparent" }}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener("webglcontextlost", (e) => {
            e.preventDefault();
            setContextLost(true);
          });
        }}
      >
        <ambientLight intensity={0.5} />
        <directionalLight position={[2, 3, 2]} intensity={0.8} />
        <directionalLight position={[-1, 2, -1]} intensity={0.3} />
        <VRMScene
          modelUrl={modelUrl}
          emotion={emotion}
          audioLevel={audioLevel}
          isSpeaking={isSpeaking}
        />
      </Canvas>
    </div>
  );
}

export default VRMAvatar;
