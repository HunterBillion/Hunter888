/**
 * TalkingHead avatar configuration.
 * Maps Hunter888 archetypes, emotions, and genders to avatar models and behaviors.
 */

// ─── Avatar Models (Ready Player Me GLB) ───────────────────────────────────

export interface AvatarModel {
  id: string;
  url: string;
  label: string;
  body: "M" | "F";
}

// GLB models hosted on TalkingHead GitHub Pages (RPM shut down Jan 2026).
// All models have ARKit + Oculus Viseme blend shapes baked in (72 morph targets).
// TODO: Replace with custom Avaturn/MPFB models matching our character profiles.
export const AVATAR_MODELS: Record<string, AvatarModel> = {
  male_young: {
    id: "male_young",
    url: "https://met4citizen.github.io/TalkingHead/avatars/avatarsdk.glb",
    label: "Мужчина",
    body: "M",
  },
  male_senior: {
    id: "male_senior",
    url: "https://met4citizen.github.io/TalkingHead/avatars/avatarsdk.glb",
    label: "Мужчина постарше",
    body: "M",
    // NOTE: Same model as male_young — need custom MPFB/Avaturn senior model
  },
  female: {
    id: "female",
    url: "https://met4citizen.github.io/TalkingHead/avatars/brunette.glb",
    label: "Женщина",
    body: "F",
  },
  female_realistic: {
    id: "female_realistic",
    url: "https://met4citizen.github.io/TalkingHead/avatars/avaturn.glb",
    label: "Женщина (реалистичная)",
    body: "F",
  },
};

// Fallback model if archetype not mapped
export const DEFAULT_MODEL = AVATAR_MODELS.male_young;

// ─── Archetype → Model Mapping ─────────────────────────────────────────────

export function getAvatarModel(
  archetypeCode: string,
  gender: "M" | "F" | "neutral" = "M"
): AvatarModel {
  // Gender-first selection
  if (gender === "F") return AVATAR_MODELS.female;

  // Archetype-based selection for males
  const seniorArchetypes = new Set([
    "paranoid", "know_it_all", "stubborn", "desperate", "overwhelmed",
    "retired", "blamer", "conspiracy", "righteous", "litigious",
    "scorched_earth", "couple", "delegator", "auditor", "power_player",
  ]);

  if (seniorArchetypes.has(archetypeCode)) {
    return AVATAR_MODELS.male_senior;
  }

  return AVATAR_MODELS.male_young;
}

// ─── Emotion → TalkingHead Mood + Gesture Mapping ──────────────────────────

export interface EmotionConfig {
  mood: string;                        // TalkingHead mood: neutral, happy, angry, sad, fear, disgust, love
  gesture: string | null;              // TalkingHead gesture: handup, index, ok, thumbup, thumbdown, side, shrug
  idleGestures: string[];             // Random idle gestures for this emotion
  breathingSpeed: number;              // 0.5 = slow (calm), 2.0 = fast (agitated)
  headMovement: number;                // 0 = still, 1 = normal, 2 = agitated
  lookAtUser: boolean;                 // Whether to track cursor/center
  transitionGesture: string | null;    // Gesture to play when transitioning TO this emotion
}

export const EMOTION_CONFIG: Record<string, EmotionConfig> = {
  cold: {
    mood: "neutral",
    gesture: null,
    idleGestures: ["side"],
    breathingSpeed: 0.7,
    headMovement: 0.3,
    lookAtUser: false,           // Avoids eye contact
    transitionGesture: null,
  },
  guarded: {
    mood: "angry",
    gesture: "side",              // Arms crossed vibe
    idleGestures: ["side", "shrug"],
    breathingSpeed: 0.9,
    headMovement: 0.5,
    lookAtUser: true,
    transitionGesture: "side",
  },
  curious: {
    mood: "happy",
    gesture: "index",             // Points, engaged
    idleGestures: ["index", "handup"],
    breathingSpeed: 1.0,
    headMovement: 1.0,
    lookAtUser: true,
    transitionGesture: "handup",
  },
  considering: {
    mood: "neutral",
    gesture: "handup",            // Thinking pose
    idleGestures: ["handup", "index"],
    breathingSpeed: 0.8,
    headMovement: 0.7,
    lookAtUser: true,
    transitionGesture: "handup",
  },
  negotiating: {
    mood: "happy",
    gesture: "ok",                // OK gesture
    idleGestures: ["ok", "index", "handup"],
    breathingSpeed: 1.0,
    headMovement: 1.0,
    lookAtUser: true,
    transitionGesture: "ok",
  },
  deal: {
    mood: "happy",
    gesture: "thumbup",           // Agreement!
    idleGestures: ["thumbup", "ok"],
    breathingSpeed: 1.0,
    headMovement: 1.2,
    lookAtUser: true,
    transitionGesture: "thumbup",
  },
  testing: {
    mood: "angry",
    gesture: "index",             // Challenging
    idleGestures: ["index", "side"],
    breathingSpeed: 1.3,
    headMovement: 1.5,
    lookAtUser: true,
    transitionGesture: "index",
  },
  callback: {
    mood: "neutral",
    gesture: "side",              // Looking away
    idleGestures: ["side", "shrug"],
    breathingSpeed: 0.8,
    headMovement: 0.5,
    lookAtUser: false,
    transitionGesture: "side",
  },
  hostile: {
    mood: "angry",
    gesture: "side",              // Hostile stance
    idleGestures: ["side", "thumbdown"],
    breathingSpeed: 1.8,
    headMovement: 2.0,
    lookAtUser: true,
    transitionGesture: "thumbdown",
  },
  hangup: {
    mood: "angry",
    gesture: "shrug",             // Gives up
    idleGestures: ["shrug"],
    breathingSpeed: 1.5,
    headMovement: 0.5,
    lookAtUser: false,
    transitionGesture: "shrug",
  },
};

export const DEFAULT_EMOTION = EMOTION_CONFIG.cold;

// ─── Idle Behavior Timing ──────────────────────────────────────────────────

export const IDLE_CONFIG = {
  gestureIntervalMin: 5000,          // Min ms between random gestures
  gestureIntervalMax: 15000,         // Max ms between random gestures
  silenceReactionDelay: 10000,       // After 10s silence → raise eyebrow
  listeningNodInterval: 3000,        // Nod every 3s while user speaks
  emotionTransitionDuration: 800,    // ms for mood crossfade
};

// ─── TalkingHead Init Options ──────────────────────────────────────────────

export const TALKING_HEAD_OPTIONS = {
  ttsLang: "ru-RU",
  lipsyncLang: "en",               // Viseme set (ARKit/Oculus — language-independent)
  cameraView: "upper" as const,      // "full" | "upper" | "head"
  cameraDistance: 0.4,
  cameraX: 0,
  cameraY: 0,
  cameraRotateX: 0,
  cameraRotateY: 0,
  avatarMood: "neutral",
  avatarMute: true,                 // We handle audio playback ourselves
  markedOptions: {},
  statsDiv: null,
  modelFPS: 30,
  modelPixelRatio: 1.5,
};

// ─── Emotion Color Map (for background glow, kept from existing system) ────

export const EMOTION_COLORS: Record<string, string> = {
  cold: "var(--text-muted)",
  guarded: "var(--accent)",
  curious: "var(--warning)",
  considering: "var(--success)",
  negotiating: "#06B6D4",
  deal: "var(--success)",
  testing: "var(--danger)",
  callback: "var(--accent)",
  hostile: "var(--danger)",
  hangup: "var(--text-muted)",
};
