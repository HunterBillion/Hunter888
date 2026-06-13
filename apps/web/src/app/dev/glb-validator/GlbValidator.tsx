"use client";

/**
 * GlbValidator — drag-and-drop GLB inspector for Hunter888 avatars.
 *
 * Validates artist-delivered models against the requirements in
 * `docs/ARTIST_TZ_50_AVATARS.md`. Shows green/red checks for:
 *   - Mixamo skeleton bones (16 critical bones)
 *   - ARKit 52 facial blendshapes
 *   - Oculus 15 visemes
 *   - File size and polygon count
 * Plus a 3D preview of the loaded model.
 *
 * Public route — no auth gate. Will be locked behind admin role before pilot
 * goes live (TODO: add role guard once auth pipeline is ready for /dev/* paths).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import {
  REQUIRED_ARKIT_BLENDSHAPES,
  REQUIRED_OCULUS_VISEMES,
  REQUIRED_MIXAMO_BONES,
  RECOMMENDED_BLENDSHAPES,
  MAX_FILE_SIZE_BYTES,
  RECOMMENDED_FILE_SIZE_BYTES,
  MAX_TRIANGLES,
  RECOMMENDED_TRIANGLES,
} from "./requirements";

// ─── Types ────────────────────────────────────────────────────────────────────

interface CheckItem {
  name: string;
  found: boolean;
}

interface ValidationResult {
  fileName: string;
  fileSize: number;
  meshCount: number;
  triangleCount: number;
  textureCount: number;
  materialCount: number;
  totalBlendshapes: number; // total morph targets present (any name)
  bones: CheckItem[];
  arkit: CheckItem[];
  oculus: CheckItem[];
  recommended: CheckItem[];
  unknownBlendshapes: string[]; // morph targets present but not in our spec
  errors: string[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

/**
 * Walk the loaded scene, gather mesh/material/texture stats and the union of
 * all morph target names. Bones are gathered separately by traversing for
 * `Bone` instances (and by walking skinned mesh skeletons).
 */
function inspectGltf(
  gltfScene: THREE.Object3D,
  fileName: string,
  fileSize: number,
): ValidationResult {
  const errors: string[] = [];
  const morphNames = new Set<string>();
  const boneNames = new Set<string>();
  const textures = new Set<THREE.Texture>();
  const materials = new Set<THREE.Material>();
  let meshCount = 0;
  let triangleCount = 0;

  gltfScene.traverse((obj) => {
    // Bones — both standalone and from skeleton
    if ((obj as THREE.Bone).isBone) {
      boneNames.add(obj.name);
    }

    // Meshes — count, triangles, morph targets, materials, textures
    const mesh = obj as THREE.Mesh;
    if (mesh.isMesh) {
      meshCount += 1;

      // Triangles — for indexed geometry use index.count / 3, otherwise
      // position.count / 3 (assumes triangles, which is GLB default).
      const geo = mesh.geometry;
      if (geo) {
        const idx = geo.index;
        const pos = geo.attributes.position;
        if (idx) triangleCount += Math.floor(idx.count / 3);
        else if (pos) triangleCount += Math.floor(pos.count / 3);
      }

      // Morph target names
      if (mesh.morphTargetDictionary) {
        for (const name of Object.keys(mesh.morphTargetDictionary)) {
          morphNames.add(name);
        }
      }

      // Materials and textures
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const mat of mats) {
        if (!mat) continue;
        materials.add(mat);
        // Walk all texture-typed properties on the material
        for (const key of Object.keys(mat) as Array<keyof THREE.Material>) {
          const value = (mat as unknown as Record<string, unknown>)[
            key as string
          ];
          if (value && (value as THREE.Texture).isTexture) {
            textures.add(value as THREE.Texture);
          }
        }
      }

      // Skinned meshes carry their own skeleton — pull bone names from there too
      const skinned = mesh as unknown as THREE.SkinnedMesh;
      if (skinned.isSkinnedMesh && skinned.skeleton) {
        for (const b of skinned.skeleton.bones) boneNames.add(b.name);
      }
    }
  });

  // Build check lists
  const bones: CheckItem[] = REQUIRED_MIXAMO_BONES.map((name) => ({
    name,
    found: boneNames.has(name),
  }));
  const arkit: CheckItem[] = REQUIRED_ARKIT_BLENDSHAPES.map((name) => ({
    name,
    found: morphNames.has(name),
  }));
  const oculus: CheckItem[] = REQUIRED_OCULUS_VISEMES.map((name) => ({
    name,
    found: morphNames.has(name),
  }));
  const recommended: CheckItem[] = RECOMMENDED_BLENDSHAPES.map((name) => ({
    name,
    found: morphNames.has(name),
  }));

  // Unknown morph targets — present in file but not in our spec (might be
  // typos like "mouth_open" instead of "mouthOpen"). Help artist debug.
  const knownNames = new Set<string>([
    ...REQUIRED_ARKIT_BLENDSHAPES,
    ...REQUIRED_OCULUS_VISEMES,
    ...RECOMMENDED_BLENDSHAPES,
  ]);
  const unknownBlendshapes = [...morphNames].filter((n) => !knownNames.has(n));

  // High-level errors
  if (fileSize > MAX_FILE_SIZE_BYTES) {
    errors.push(
      `File size ${formatBytes(fileSize)} exceeds hard cap ${formatBytes(MAX_FILE_SIZE_BYTES)}`,
    );
  }
  if (triangleCount > MAX_TRIANGLES) {
    errors.push(
      `Triangle count ${triangleCount} exceeds hard cap ${MAX_TRIANGLES}`,
    );
  }
  if (boneNames.size === 0) {
    errors.push(
      "No bones found — model has no skeleton. TalkingHead requires Mixamo rig.",
    );
  }
  if (morphNames.size === 0) {
    errors.push(
      "No morph targets found — model has no blendshapes. Lipsync and emotions will not work.",
    );
  }

  return {
    fileName,
    fileSize,
    meshCount,
    triangleCount,
    textureCount: textures.size,
    materialCount: materials.size,
    totalBlendshapes: morphNames.size,
    bones,
    arkit,
    oculus,
    recommended,
    unknownBlendshapes,
    errors,
  };
}

// ─── Component ────────────────────────────────────────────────────────────────

export function GlbValidator() {
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const previewRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<{
    scene?: THREE.Scene;
    camera?: THREE.PerspectiveCamera;
    renderer?: THREE.WebGLRenderer;
    mixer?: THREE.AnimationMixer;
    avatar?: THREE.Object3D;
    rafId?: number;
  }>({});

  // ── Three.js preview setup (one-time) ──
  useEffect(() => {
    if (!previewRef.current) return;
    const container = previewRef.current;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x111114);
    const camera = new THREE.PerspectiveCamera(
      35,
      container.clientWidth / container.clientHeight,
      0.01,
      100,
    );
    camera.position.set(0, 1.5, 1.0);
    camera.lookAt(0, 1.4, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);

    // Three-point lighting — neutral, lets the artist judge skin tones.
    scene.add(new THREE.AmbientLight(0xffffff, 0.4));
    const key = new THREE.DirectionalLight(0xffffff, 0.9);
    key.position.set(2, 3, 2);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x99aaff, 0.3);
    fill.position.set(-2, 1, -1);
    scene.add(fill);

    const animate = () => {
      sceneRef.current.rafId = requestAnimationFrame(animate);
      const avatar = sceneRef.current.avatar;
      if (avatar) avatar.rotation.y += 0.005;
      renderer.render(scene, camera);
    };
    animate();

    sceneRef.current = { scene, camera, renderer };

    const onResize = () => {
      if (!container) return;
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      if (sceneRef.current.rafId) cancelAnimationFrame(sceneRef.current.rafId);
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      sceneRef.current = {};
    };
  }, []);

  // ── File handling ──
  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setResult(null);
    setLoading(true);

    try {
      if (!file.name.toLowerCase().endsWith(".glb")) {
        throw new Error("File must be a .glb (binary glTF). Got: " + file.name);
      }
      const buffer = await file.arrayBuffer();

      // Parse via GLTFLoader — supports Draco-compressed glTF
      const loader = new GLTFLoader();
      const gltf = await new Promise<{ scene: THREE.Object3D }>((resolve, reject) => {
        loader.parse(
          buffer,
          "",
          (g: { scene: THREE.Object3D }) => resolve(g),
          (err: ErrorEvent) => reject(err),
        );
      });

      // Run inspection BEFORE swapping into preview scene (so morph targets and
      // bones are read from the freshly-parsed tree without our preview's
      // interferences).
      const validation = inspectGltf(gltf.scene, file.name, file.size);

      // Replace preview content
      const refs = sceneRef.current;
      if (refs.scene) {
        if (refs.avatar) refs.scene.remove(refs.avatar);
        refs.avatar = gltf.scene;
        // Center the model so the head lands roughly at camera height (~1.4m)
        const bbox = new THREE.Box3().setFromObject(gltf.scene);
        const size = new THREE.Vector3();
        bbox.getSize(size);
        const center = new THREE.Vector3();
        bbox.getCenter(center);
        gltf.scene.position.sub(center);
        gltf.scene.position.y += size.y / 2;
        refs.scene.add(gltf.scene);
        // Auto-frame camera based on object size
        const fitDist = Math.max(size.x, size.y) * 1.6;
        if (refs.camera) {
          refs.camera.position.set(0, size.y * 0.85, fitDist);
          refs.camera.lookAt(0, size.y * 0.85, 0);
        }
      }

      setResult(validation);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Drag handlers
  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      const f = e.dataTransfer.files[0];
      if (f) void handleFile(f);
    },
    [handleFile],
  );
  const onDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(true);
  }, []);
  const onDragLeave = useCallback(() => setDragOver(false), []);
  const onFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (f) void handleFile(f);
    },
    [handleFile],
  );

  // ── Derived metrics for summary header ──
  const summary = result
    ? {
        bonesOk: result.bones.filter((b) => b.found).length,
        bonesTotal: result.bones.length,
        arkitOk: result.arkit.filter((b) => b.found).length,
        arkitTotal: result.arkit.length,
        oculusOk: result.oculus.filter((b) => b.found).length,
        oculusTotal: result.oculus.length,
        sizeOk: result.fileSize <= MAX_FILE_SIZE_BYTES,
        sizeWarn:
          result.fileSize > RECOMMENDED_FILE_SIZE_BYTES &&
          result.fileSize <= MAX_FILE_SIZE_BYTES,
        trianglesOk: result.triangleCount <= MAX_TRIANGLES,
        trianglesWarn:
          result.triangleCount > RECOMMENDED_TRIANGLES &&
          result.triangleCount <= MAX_TRIANGLES,
      }
    : null;

  const allRequiredPass =
    summary &&
    summary.bonesOk === summary.bonesTotal &&
    summary.arkitOk === summary.arkitTotal &&
    summary.oculusOk === summary.oculusTotal &&
    summary.sizeOk &&
    summary.trianglesOk &&
    result?.errors.length === 0;

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 px-6 py-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold">GLB Validator — Hunter888</h1>
          <p className="text-sm text-neutral-400 mt-1">
            Drag a <code>.glb</code> file here to validate it against the artist TZ
            requirements (52 ARKit blendshapes + 15 Oculus visemes + Mixamo rig + size limits).
          </p>
        </header>

        {/* Drop zone */}
        <div
          onDrop={onDrop}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          className={`rounded-xl border-2 border-dashed transition-colors p-8 text-center mb-6 ${
            dragOver
              ? "border-violet-400 bg-violet-500/10"
              : "border-neutral-700 bg-neutral-900"
          }`}
        >
          <p className="text-neutral-300 mb-3">
            {loading
              ? "Loading and inspecting model…"
              : "Drop a .glb file here, or click to browse"}
          </p>
          <input
            type="file"
            accept=".glb"
            onChange={onFileInput}
            disabled={loading}
            className="block mx-auto text-sm text-neutral-400 file:mr-3 file:rounded file:border-0 file:bg-violet-600 file:text-white file:px-3 file:py-1 file:cursor-pointer"
          />
          {error && (
            <p className="text-red-400 text-sm mt-3 font-mono">{error}</p>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: 3D preview */}
          <section>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-400 mb-2">
              Preview
            </h2>
            <div
              ref={previewRef}
              className="aspect-square w-full rounded-lg bg-neutral-900 border border-neutral-800 overflow-hidden"
            />
            <p className="text-xs text-neutral-500 mt-2">
              Auto-rotates. Camera positioned at avatar's head height. Lipsync test
              page is at <code>/dev/talkinghead-test</code> (coming next).
            </p>
          </section>

          {/* Right: validation results */}
          <section>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-400 mb-2">
              Validation Report
            </h2>

            {!result && !loading && (
              <p className="text-neutral-500 text-sm italic">
                No file loaded yet.
              </p>
            )}

            {result && summary && (
              <div className="space-y-4">
                {/* Pass/fail banner */}
                <div
                  className={`rounded-lg p-3 text-center font-semibold ${
                    allRequiredPass
                      ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                      : "bg-red-500/15 text-red-300 border border-red-500/30"
                  }`}
                >
                  {allRequiredPass
                    ? "✅ ALL CHECKS PASSED — model accepted"
                    : "❌ MODEL HAS ISSUES — see details below"}
                </div>

                {/* File-level metrics */}
                <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-4 text-sm">
                  <div className="font-mono text-neutral-300 mb-2">
                    {result.fileName}
                  </div>
                  <ul className="space-y-1 text-neutral-400">
                    <Stat
                      label="File size"
                      value={formatBytes(result.fileSize)}
                      ok={summary.sizeOk}
                      warn={summary.sizeWarn}
                      detail={
                        summary.sizeWarn
                          ? `over recommended ${formatBytes(RECOMMENDED_FILE_SIZE_BYTES)}`
                          : undefined
                      }
                    />
                    <Stat
                      label="Triangles"
                      value={result.triangleCount.toLocaleString()}
                      ok={summary.trianglesOk}
                      warn={summary.trianglesWarn}
                      detail={
                        summary.trianglesWarn
                          ? `over recommended ${RECOMMENDED_TRIANGLES.toLocaleString()}`
                          : undefined
                      }
                    />
                    <Stat
                      label="Meshes"
                      value={String(result.meshCount)}
                      ok={result.meshCount > 0}
                    />
                    <Stat
                      label="Materials"
                      value={String(result.materialCount)}
                      ok={result.materialCount > 0}
                    />
                    <Stat
                      label="Textures"
                      value={String(result.textureCount)}
                      ok={result.textureCount > 0}
                    />
                    <Stat
                      label="Total blendshapes"
                      value={String(result.totalBlendshapes)}
                      ok={result.totalBlendshapes >= 67}
                    />
                  </ul>
                </div>

                {/* Required check groups */}
                <CheckGroup
                  title="Mixamo Skeleton Bones"
                  items={result.bones}
                  okCount={summary.bonesOk}
                  total={summary.bonesTotal}
                />
                <CheckGroup
                  title="ARKit 52 Blendshapes"
                  items={result.arkit}
                  okCount={summary.arkitOk}
                  total={summary.arkitTotal}
                />
                <CheckGroup
                  title="Oculus 15 Visemes"
                  items={result.oculus}
                  okCount={summary.oculusOk}
                  total={summary.oculusTotal}
                />
                <CheckGroup
                  title="Recommended (optional)"
                  items={result.recommended}
                  okCount={result.recommended.filter((r) => r.found).length}
                  total={result.recommended.length}
                  optional
                />

                {/* Unknown blendshapes — typo detector */}
                {result.unknownBlendshapes.length > 0 && (
                  <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 p-3 text-sm">
                    <div className="font-semibold text-amber-300 mb-1">
                      ⚠️ Found {result.unknownBlendshapes.length} blendshape(s) NOT
                      in spec — possible typos:
                    </div>
                    <ul className="font-mono text-xs text-amber-200/80 list-disc pl-5 space-y-0.5">
                      {result.unknownBlendshapes.slice(0, 30).map((n) => (
                        <li key={n}>{n}</li>
                      ))}
                      {result.unknownBlendshapes.length > 30 && (
                        <li className="italic opacity-70">
                          …and {result.unknownBlendshapes.length - 30} more
                        </li>
                      )}
                    </ul>
                  </div>
                )}

                {/* Hard errors */}
                {result.errors.length > 0 && (
                  <div className="rounded-lg bg-red-500/10 border border-red-500/30 p-3 text-sm">
                    <div className="font-semibold text-red-300 mb-1">
                      Errors:
                    </div>
                    <ul className="text-red-200/80 list-disc pl-5 space-y-0.5">
                      {result.errors.map((err, i) => (
                        <li key={i}>{err}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>

        {/* Footer note for artist */}
        <footer className="mt-10 text-xs text-neutral-500 border-t border-neutral-800 pt-4">
          <p>
            Spec source: <code>docs/ARTIST_TZ_50_AVATARS.md</code>. If you see a
            requirement here that contradicts the TZ doc, the TZ wins — please
            ping the frontend team to fix this validator.
          </p>
        </footer>
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function Stat({
  label,
  value,
  ok,
  warn,
  detail,
}: {
  label: string;
  value: string;
  ok: boolean;
  warn?: boolean;
  detail?: string;
}) {
  const icon = ok ? (warn ? "⚠️" : "✅") : "❌";
  const color = ok
    ? warn
      ? "text-amber-300"
      : "text-emerald-300"
    : "text-red-300";
  return (
    <li className="flex items-baseline gap-2">
      <span className={color}>{icon}</span>
      <span className="text-neutral-400">{label}:</span>
      <span className="font-mono text-neutral-200">{value}</span>
      {detail && <span className="text-xs text-neutral-500">({detail})</span>}
    </li>
  );
}

function CheckGroup({
  title,
  items,
  okCount,
  total,
  optional = false,
}: {
  title: string;
  items: CheckItem[];
  okCount: number;
  total: number;
  optional?: boolean;
}) {
  const pass = optional ? true : okCount === total;
  return (
    <div className="rounded-lg bg-neutral-900 border border-neutral-800 overflow-hidden">
      <header
        className={`flex items-center justify-between px-4 py-2 text-sm font-semibold border-b border-neutral-800 ${
          pass ? "text-emerald-300" : "text-red-300"
        }`}
      >
        <span>{title}{optional && <span className="ml-2 text-xs text-neutral-500 font-normal">(optional)</span>}</span>
        <span className="font-mono">
          {okCount} / {total}
        </span>
      </header>
      <ul className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-0.5 p-3 text-xs font-mono">
        {items.map((it) => (
          <li
            key={it.name}
            className={`flex items-baseline gap-1.5 ${
              it.found ? "text-emerald-300/90" : "text-red-300/80"
            }`}
          >
            <span className="opacity-60">{it.found ? "✓" : "✗"}</span>
            <span className="truncate" title={it.name}>
              {it.name}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
