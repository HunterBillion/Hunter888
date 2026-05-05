"use client";

import { useState } from "react";
import type { MicErrorReason } from "@/types";
import type { SpeechErrorCode } from "@/hooks/useSpeechRecognition";

// Single source of truth for the "voice is unavailable" banner shown
// during a call. Replaces the old `fixed top-[130px] bg-amber-500/90`
// overlay that:
//  • used a hard-coded 130px offset and overlapped the scenario text
//    on smaller viewports;
//  • showed the same generic "Микрофон недоступен" copy regardless of
//    the underlying cause (denied vs no-device vs in-use vs HTTP-only
//    vs unsupported browser vs autoplay block);
//  • was `pointer-events-none` for the most common "unsupported"
//    branch — user couldn't dismiss it or learn anything.
//
// Now: a sticky bar that sits *between* the header and the call
// content (so it doesn't occlude anything), tells the user *why* mic
// is down, and offers a primary action (retry / open settings hint).

export type MicBannerKind =
  | "ws_dead"             // websocket reconnect — server side, mic is fine
  | "stt_denied"          // microphone permission revoked / not granted
  | "stt_not_found"       // no input device on the system
  | "stt_in_use"          // device captured by another app (Zoom etc.)
  | "stt_insecure"        // not HTTPS
  | "stt_constraints"     // sample rate / channel constraints failed
  | "stt_unsupported"     // browser has no SpeechRecognition / getUserMedia
  | "stt_network"         // SpeechRecognition network error
  | "stt_audio_capture"   // audio-capture failed (hardware fault)
  | "stt_unknown";        // generic fallback

export interface MicStatusBannerProps {
  kind: MicBannerKind;
  onRetry?: () => void;
}

interface BannerCopy {
  title: string;
  hint: string;
  action: { label: string; kind: "retry" | "dismiss" } | null;
  /** Whether the banner is the user's fault (yellow) or ours (red).  */
  severity: "info" | "warn" | "error";
}

const COPY: Record<MicBannerKind, BannerCopy> = {
  ws_dead: {
    title: "Нет связи с сервером",
    hint: "Переподключаемся автоматически — подождите несколько секунд.",
    action: null,
    severity: "warn",
  },
  stt_denied: {
    title: "Доступ к микрофону запрещён",
    hint: "Нажмите на иконку 🔒 / 🎙 в адресной строке и разрешите микрофон, затем попробуйте снова. Или пишите текстом снизу.",
    action: { label: "Повторить", kind: "retry" },
    severity: "warn",
  },
  stt_not_found: {
    title: "Микрофон не найден",
    hint: "Подключите наушники с микрофоном или внешний микрофон и нажмите «Повторить». Можно продолжать текстом снизу.",
    action: { label: "Повторить", kind: "retry" },
    severity: "warn",
  },
  stt_in_use: {
    title: "Микрофон занят другим приложением",
    hint: "Закройте Zoom / Discord / Meet и нажмите «Повторить». Эксклюзивный захват — на одно приложение за раз.",
    action: { label: "Повторить", kind: "retry" },
    severity: "warn",
  },
  stt_insecure: {
    title: "Браузер блокирует микрофон",
    hint: "Микрофон работает только через HTTPS. Откройте сайт по защищённой ссылке или обратитесь к администратору.",
    action: null,
    severity: "error",
  },
  stt_constraints: {
    title: "Микрофон не поддерживает нужный формат",
    hint: "Попробуйте другой микрофон или другой браузер. Текстовый ввод снизу работает в любом случае.",
    action: { label: "Повторить", kind: "retry" },
    severity: "warn",
  },
  stt_unsupported: {
    title: "Голос в этом браузере не работает",
    hint: "Откройте x-hunter.expert в Google Chrome или Microsoft Edge — там голосовой ввод работает стабильно. В Brave включите «Speech Recognition» в Shield-настройках сайта. В Safari нужна версия ≥ 14.1. Текстовый ввод снизу работает в любом браузере.",
    action: null,
    severity: "info",
  },
  stt_network: {
    // 2026-05-05: refined after prod feedback. Banner used to say only
    // «проверьте интернет» — but the real cause for 90% of users is
    // Brave's Shield blocking the Web Speech cloud, or Safari/Firefox
    // not exposing the API at all. Shifted to a concrete remediation
    // that names the browsers + Brave-specific toggle the user can
    // try without opening DevTools.
    title: "Голосовое распознавание заблокировано",
    hint: "Web Speech API использует облако Google. В Brave его блокирует Shields — откройте Shields этого сайта и включите «Speech Recognition». В Safari/Firefox API нет — лучше Chrome или Edge. Текстовый ввод снизу работает прямо сейчас, без переключения браузера.",
    action: { label: "Повторить", kind: "retry" },
    severity: "warn",
  },
  stt_audio_capture: {
    title: "Не удалось захватить звук с микрофона",
    hint: "Похоже на аппаратную проблему — переподключите устройство. Текстовый ввод снизу остаётся доступен.",
    action: { label: "Повторить", kind: "retry" },
    severity: "warn",
  },
  stt_unknown: {
    title: "Микрофон недоступен",
    hint: "Не удалось определить причину. Попробуйте повторить или продолжайте текстом снизу.",
    action: { label: "Повторить", kind: "retry" },
    severity: "warn",
  },
};

const SEVERITY_STYLES: Record<BannerCopy["severity"], string> = {
  // Solid backgrounds (no /90 transparency) so text under the banner
  // never bleeds through. Border + shadow give clear separation.
  info: "bg-slate-800 text-white border-slate-600",
  warn: "bg-amber-600 text-black border-amber-700",
  error: "bg-rose-600 text-white border-rose-700",
};

export function MicStatusBanner({ kind, onRetry }: MicStatusBannerProps) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const copy = COPY[kind];
  const styles = SEVERITY_STYLES[copy.severity];

  return (
    <div
      role={copy.severity === "info" ? "status" : "alert"}
      aria-live="polite"
      // sticky — flows with content under the header, never covers the
      // scenario card. z-30 keeps it above page content but below the
      // text-input bar (z-20 inverted by autoplay-overlay z-9999).
      className={`sticky top-0 z-30 mx-auto w-full max-w-3xl px-4 pt-2`}
    >
      <div
        className={`flex items-start gap-3 rounded-xl border px-4 py-3 shadow-lg ${styles}`}
      >
        <div className="flex-1 text-sm">
          <div className="font-semibold">{copy.title}</div>
          <div className="mt-0.5 text-xs opacity-90">{copy.hint}</div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {copy.action?.kind === "retry" && onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="rounded-md bg-black/20 px-3 py-1 text-xs font-medium hover:bg-black/30"
            >
              {copy.action.label}
            </button>
          )}
          <button
            type="button"
            aria-label="Закрыть"
            onClick={() => setDismissed(true)}
            className="rounded-md px-2 py-1 text-xs opacity-70 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
}

// Helper to map (wsDead, sttSupported, sttErrorCode, micErrorReason)
// → a single banner kind. Centralised so the call/chat pages don't
// have to repeat the precedence rules. Returns null when nothing
// should be shown.
export function pickBannerKind(args: {
  wsDead: boolean;
  sttSupported: boolean;
  sttErrorCode: SpeechErrorCode | null;
  micErrorReason: MicErrorReason | null;
}): MicBannerKind | null {
  const { wsDead, sttSupported, sttErrorCode, micErrorReason } = args;
  // Server connectivity beats everything — mic doesn't matter if WS is down.
  if (wsDead) return "ws_dead";
  // Browser-level "not supported" is a property of the environment,
  // not a transient error — show it whenever no recognition is available.
  if (!sttSupported) return "stt_unsupported";
  // useMicrophone errors are richer than useSpeechRecognition — prefer them.
  if (micErrorReason) {
    switch (micErrorReason) {
      case "denied": return "stt_denied";
      case "not_found": return "stt_not_found";
      case "in_use": return "stt_in_use";
      case "insecure": return "stt_insecure";
      case "constraints": return "stt_constraints";
      case "unsupported": return "stt_unsupported";
      case "aborted": return null; // user closed prompt — don't nag
      case "unknown": return "stt_unknown";
    }
  }
  if (sttErrorCode) {
    switch (sttErrorCode) {
      case "not-allowed": return "stt_denied";
      case "audio-capture": return "stt_audio_capture";
      case "network": return "stt_network";
      case "service-not-allowed": return "stt_denied";
      case "language-not-supported": return "stt_unsupported";
      case "bad-grammar": return "stt_unknown";
      case "start-failed": return "stt_unknown";
      case "unsupported": return "stt_unsupported";
      case "unknown": return "stt_unknown";
    }
  }
  return null;
}
