/**
 * GLB Validator — required morph targets and skeleton bones for Hunter888 avatars.
 *
 * These lists are referenced from the artist TZ:
 * `docs/ARTIST_TZ_50_AVATARS.md` §2.2 and §2.3.
 *
 * Any change here MUST be mirrored in the TZ document and communicated to the artist.
 */

// ─── ARKit 52 expressions (mandatory) ─────────────────────────────────────────
// Apple ARKit standard, exact camelCase. TalkingHead reads these to drive emotion.
export const REQUIRED_ARKIT_BLENDSHAPES: readonly string[] = [
  "browDownLeft", "browDownRight", "browInnerUp",
  "browOuterUpLeft", "browOuterUpRight",
  "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
  "eyeBlinkLeft", "eyeBlinkRight",
  "eyeLookDownLeft", "eyeLookDownRight",
  "eyeLookInLeft", "eyeLookInRight",
  "eyeLookOutLeft", "eyeLookOutRight",
  "eyeLookUpLeft", "eyeLookUpRight",
  "eyeSquintLeft", "eyeSquintRight",
  "eyeWideLeft", "eyeWideRight",
  "jawForward", "jawLeft", "jawOpen", "jawRight",
  "mouthClose", "mouthDimpleLeft", "mouthDimpleRight",
  "mouthFrownLeft", "mouthFrownRight",
  "mouthFunnel", "mouthLeft", "mouthRight",
  "mouthLowerDownLeft", "mouthLowerDownRight",
  "mouthPressLeft", "mouthPressRight",
  "mouthPucker",
  "mouthRollLower", "mouthRollUpper",
  "mouthShrugLower", "mouthShrugUpper",
  "mouthSmileLeft", "mouthSmileRight",
  "mouthStretchLeft", "mouthStretchRight",
  "mouthUpperUpLeft", "mouthUpperUpRight",
  "noseSneerLeft", "noseSneerRight",
  "tongueOut",
] as const;

// ─── Oculus 15 visemes (mandatory) ────────────────────────────────────────────
// Required for lipsync. TalkingHead engine sets these every frame during speech.
export const REQUIRED_OCULUS_VISEMES: readonly string[] = [
  "sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS",
  "nn", "RR", "aa", "E", "I", "O", "U",
] as const;

// ─── Mixamo critical bones (mandatory) ────────────────────────────────────────
// Without these names exactly, TalkingHead animations will not bind.
// Subset — only the bones the engine uses for head movement, eye tracking, and gestures.
export const REQUIRED_MIXAMO_BONES: readonly string[] = [
  "mixamorigHips",
  "mixamorigSpine", "mixamorigSpine1", "mixamorigSpine2",
  "mixamorigNeck", "mixamorigHead",
  "mixamorigLeftEye", "mixamorigRightEye",
  "mixamorigLeftShoulder", "mixamorigRightShoulder",
  "mixamorigLeftArm", "mixamorigRightArm",
  "mixamorigLeftForeArm", "mixamorigRightForeArm",
  "mixamorigLeftHand", "mixamorigRightHand",
] as const;

// ─── Recommended (optional but improves quality) ──────────────────────────────
export const RECOMMENDED_BLENDSHAPES: readonly string[] = [
  "mouthOpen", "mouthSmile", "eyesClosed",
  "eyesLookUp", "eyesLookDown",
] as const;

// ─── File size and polygon limits ─────────────────────────────────────────────
export const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB hard cap
export const RECOMMENDED_FILE_SIZE_BYTES = 8 * 1024 * 1024; // 8 MB target
export const MAX_TRIANGLES = 30000; // Including bust + head (artist TZ §2.5)
export const RECOMMENDED_TRIANGLES = 20000;
