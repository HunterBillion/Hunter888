declare module "@met4citizen/talkinghead" {
  interface TalkingHeadOptions {
    ttsLang?: string;
    lipsyncLang?: string;
    cameraView?: "full" | "upper" | "head";
    cameraDistance?: number;
    cameraX?: number;
    cameraY?: number;
    cameraRotateX?: number;
    cameraRotateY?: number;
    avatarMood?: string;
    avatarMute?: boolean;
    markedOptions?: Record<string, unknown>;
    statsDiv?: HTMLElement | null;
    modelFPS?: number;
    modelPixelRatio?: number;
  }

  interface ShowAvatarOptions {
    url: string;
    body?: "M" | "F";
    avatarMood?: string;
    lipsyncLang?: string;
  }

  class TalkingHead {
    constructor(container: HTMLElement, options?: TalkingHeadOptions);
    showAvatar(
      options: ShowAvatarOptions,
      onProgress?: (ev: ProgressEvent) => void
    ): Promise<void>;
    setMood(mood: string): void;
    playGesture(name: string): void;
    playAnimation(url: string, options?: Record<string, unknown>): void;
    speakAudio(
      audio: ArrayBuffer | Blob,
      options?: Record<string, unknown>
    ): void;
    speakText(text: string, options?: Record<string, unknown>): void;
    stopSpeaking(): void;
    setLookAtTarget(x: number, y: number): void;
    start(): void;
    stop(): void;
  }

  export { TalkingHead };
}
