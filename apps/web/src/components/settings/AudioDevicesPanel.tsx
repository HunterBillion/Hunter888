"use client";

/**
 * AudioDevicesPanel — устройства ввода/вывода + микро-тест уровня + TTS preview.
 *
 * Появилось в /settings 2026-05-02 как закрытие следующих P1 находок аудита:
 *   - не было способа выбрать конкретный микрофон (enumerateDevices)
 *   - не было mic-test панели — пользователь не мог проверить уровень
 *     перед звонком
 *   - не было TTS-preview (бэк уже поддерживает голоса alloy/nova/echo/…
 *     через config.py:327, FE никак этим не пользовался)
 *
 * Все значения сохраняются в user.preferences через единый autosave-хук
 * страницы /settings (parent компонент). Этот файл — только UI.
 */

import * as React from "react";
import { motion } from "framer-motion";
import { Microphone, Headphones, Waveform, Play, Stop, Warning } from "@phosphor-icons/react";
import { logger } from "@/lib/logger";
import type { MicErrorReason } from "@/types";

interface AudioDevicesPanelProps {
  micDeviceId: string;
  speakerDeviceId: string;
  noiseSuppression: boolean;
  echoCancellation: boolean;
  ttsVoice: string;
  ttsRate: number;
  onChangeMicDevice: (id: string) => void;
  onChangeSpeakerDevice: (id: string) => void;
  onChangeNoiseSuppression: (v: boolean) => void;
  onChangeEchoCancellation: (v: boolean) => void;
  onChangeTtsVoice: (v: string) => void;
  onChangeTtsRate: (v: number) => void;
}

const TTS_VOICES = [
  { id: "default", label: "По умолчанию" },
  { id: "alloy", label: "Alloy (нейтральный)" },
  { id: "echo", label: "Echo (мужской)" },
  { id: "fable", label: "Fable (тёплый)" },
  { id: "onyx", label: "Onyx (низкий)" },
  { id: "nova", label: "Nova (женский)" },
  { id: "shimmer", label: "Shimmer (мягкий)" },
];

export function AudioDevicesPanel(props: AudioDevicesPanelProps) {
  const [inputDevices, setInputDevices] = React.useState<MediaDeviceInfo[]>([]);
  const [outputDevices, setOutputDevices] = React.useState<MediaDeviceInfo[]>([]);
  const [enumError, setEnumError] = React.useState<MicErrorReason | null>(null);
  const [permissionGranted, setPermissionGranted] = React.useState<boolean>(false);

  // Enumerate audio I/O devices. Browsers reveal labels only AFTER the
  // user has granted microphone permission at least once — before that
  // we get "Microphone" / "Speaker" with empty labels. We render them
  // anyway with a generic name so the picker still works.
  const enumerate = React.useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) {
      setEnumError("unsupported");
      return;
    }
    try {
      const list = await navigator.mediaDevices.enumerateDevices();
      setInputDevices(list.filter((d) => d.kind === "audioinput"));
      setOutputDevices(list.filter((d) => d.kind === "audiooutput"));
      // If at least one input has a non-empty label, permission has been
      // granted at some point — the labels are revealed only post-grant.
      setPermissionGranted(list.some((d) => d.kind === "audioinput" && !!d.label));
      setEnumError(null);
    } catch (err) {
      logger.warn("[AudioDevices] enumerate failed:", err);
      setEnumError("unknown");
    }
  }, []);

  React.useEffect(() => {
    enumerate();
    const handler = () => enumerate();
    if (typeof navigator !== "undefined" && navigator.mediaDevices) {
      navigator.mediaDevices.addEventListener("devicechange", handler);
      return () => {
        navigator.mediaDevices.removeEventListener("devicechange", handler);
      };
    }
    return undefined;
  }, [enumerate]);

  // ─── Mic test (level meter) ─────────────────────────────────────────────
  const [testing, setTesting] = React.useState(false);
  const [level, setLevel] = React.useState(0);
  const [testError, setTestError] = React.useState<string | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);
  const ctxRef = React.useRef<AudioContext | null>(null);
  const animRef = React.useRef(0);

  const stopTest = React.useCallback(() => {
    cancelAnimationFrame(animRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    ctxRef.current?.close().catch(() => {});
    ctxRef.current = null;
    setLevel(0);
    setTesting(false);
  }, []);

  const startTest = React.useCallback(async () => {
    setTestError(null);
    if (typeof window !== "undefined" && !window.isSecureContext) {
      setTestError("HTTPS required — открыт по HTTP, микрофон недоступен.");
      return;
    }
    try {
      const constraints: MediaStreamConstraints = {
        audio: {
          deviceId: props.micDeviceId && props.micDeviceId !== "default"
            ? { exact: props.micDeviceId } : undefined,
          echoCancellation: props.echoCancellation,
          noiseSuppression: props.noiseSuppression,
        },
      };
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;
      // Re-enumerate now that permission is granted — device labels become
      // visible post-grant.
      enumerate();
      const Ctor: typeof AudioContext =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext ||
        AudioContext;
      const ctx = new Ctor();
      if (ctx.state === "suspended") ctx.resume().catch(() => {});
      ctxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.7;
      src.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i];
        const avg = sum / data.length;
        setLevel(Math.min(100, Math.round((avg / 255) * 100 * 2)));
        animRef.current = requestAnimationFrame(tick);
      };
      tick();
      setTesting(true);
    } catch (err) {
      const name = err instanceof DOMException ? err.name : "Error";
      let msg = "Не удалось включить микрофон";
      if (name === "NotAllowedError" || name === "PermissionDeniedError") {
        msg = "Доступ к микрофону запрещён. Разрешите в настройках браузера.";
      } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
        msg = "Микрофон не найден. Подключите устройство.";
      } else if (name === "NotReadableError" || name === "TrackStartError") {
        msg = "Микрофон занят другим приложением.";
      }
      setTestError(msg);
      logger.warn("[AudioDevices] mic test failed:", { name, err });
    }
  }, [props.micDeviceId, props.echoCancellation, props.noiseSuppression, enumerate]);

  React.useEffect(() => () => stopTest(), [stopTest]);

  // ─── TTS preview ─────────────────────────────────────────────────────────
  const [previewing, setPreviewing] = React.useState(false);
  const previewAudioRef = React.useRef<HTMLAudioElement | null>(null);

  const stopPreview = React.useCallback(() => {
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current.src = "";
      previewAudioRef.current = null;
    }
    setPreviewing(false);
  }, []);

  const playPreview = React.useCallback(() => {
    // Falls back to browser speechSynthesis — backend per-user voice
    // selection isn't wired through yet (planned). For now this gives
    // the user a "does my speaker work?" sanity check with the chosen
    // rate applied.
    if (typeof window === "undefined" || !window.speechSynthesis) {
      setTestError("Браузер не поддерживает озвучку.");
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(
      "Это тестовая фраза. Так будет звучать ваш виртуальный клиент во время звонка.",
    );
    u.lang = "ru-RU";
    u.rate = props.ttsRate;
    u.onend = () => setPreviewing(false);
    u.onerror = () => setPreviewing(false);
    window.speechSynthesis.speak(u);
    setPreviewing(true);
  }, [props.ttsRate]);

  React.useEffect(() => () => stopPreview(), [stopPreview]);

  // ─── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="space-y-3">
      {/* Mic device picker + test */}
      <div className="glass-panel rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <Microphone weight="duotone" size={18} style={{ color: "var(--accent)" }} />
          <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
            Микрофон
          </div>
        </div>

        <label className="block text-xs uppercase tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>
          Устройство ввода
        </label>
        <select
          value={props.micDeviceId || "default"}
          onChange={(e) => props.onChangeMicDevice(e.target.value)}
          className="w-full rounded-lg px-3 py-2 text-sm outline-none mb-3"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
            color: "var(--text-primary)",
          }}
        >
          <option value="default">Системное (по умолчанию)</option>
          {inputDevices.map((d) => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.label || `Микрофон ${d.deviceId.slice(0, 6)}`}
            </option>
          ))}
        </select>

        {!permissionGranted && inputDevices.length > 0 && (
          <p className="text-xs flex items-start gap-1.5 mb-3" style={{ color: "var(--text-muted)" }}>
            <Warning weight="duotone" size={14} style={{ color: "var(--warning)", flexShrink: 0, marginTop: 1 }} />
            <span>Названия микрофонов появятся после первого разрешения. Нажмите «Тест» — браузер попросит доступ.</span>
          </p>
        )}

        <div className="flex items-center gap-3 mb-3">
          {!testing ? (
            <motion.button
              type="button"
              onClick={startTest}
              whileTap={{ scale: 0.96 }}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
              style={{ background: "var(--accent-muted)", color: "var(--accent)", border: "1px solid var(--accent)" }}
            >
              <Play weight="fill" size={12} /> Тест
            </motion.button>
          ) : (
            <motion.button
              type="button"
              onClick={stopTest}
              whileTap={{ scale: 0.96 }}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
              style={{ background: "var(--danger-muted)", color: "var(--danger)", border: "1px solid var(--danger)" }}
            >
              <Stop weight="fill" size={12} /> Стоп
            </motion.button>
          )}
          <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
            <div
              className="h-full transition-all duration-75"
              style={{
                width: `${level}%`,
                background: level > 80
                  ? "var(--danger)"
                  : level > 50
                    ? "var(--warning)"
                    : "var(--success, var(--accent))",
              }}
            />
          </div>
          <span className="text-xs font-mono tabular-nums w-9 text-right" style={{ color: level > 0 ? "var(--accent)" : "var(--text-muted)" }}>
            {level}%
          </span>
        </div>

        {testError && (
          <p className="text-xs rounded-md p-2 mb-3" style={{ background: "var(--danger-muted)", color: "var(--danger)" }}>
            {testError}
          </p>
        )}
        {enumError === "unsupported" && (
          <p className="text-xs rounded-md p-2 mb-3" style={{ background: "var(--warning-muted, var(--input-bg))", color: "var(--warning)" }}>
            Этот браузер не умеет перечислять устройства — оставьте «по умолчанию».
          </p>
        )}

        {/* Constraints toggles */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <ToggleRow
            label="Шумоподавление"
            hint="Убирает шум вентилятора, клавиатуры"
            on={props.noiseSuppression}
            onChange={() => props.onChangeNoiseSuppression(!props.noiseSuppression)}
          />
          <ToggleRow
            label="Эхоподавление"
            hint="Убирает эхо от колонок"
            on={props.echoCancellation}
            onChange={() => props.onChangeEchoCancellation(!props.echoCancellation)}
          />
        </div>
      </div>

      {/* Speaker / output device + TTS preview */}
      <div className="glass-panel rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <Headphones weight="duotone" size={18} style={{ color: "var(--accent)" }} />
          <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
            Динамики и голос клиента
          </div>
        </div>

        <label className="block text-xs uppercase tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>
          Устройство вывода
        </label>
        <select
          value={props.speakerDeviceId || "default"}
          onChange={(e) => props.onChangeSpeakerDevice(e.target.value)}
          className="w-full rounded-lg px-3 py-2 text-sm outline-none mb-3"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
            color: "var(--text-primary)",
          }}
        >
          <option value="default">Системное (по умолчанию)</option>
          {outputDevices.map((d) => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.label || `Динамик ${d.deviceId.slice(0, 6)}`}
            </option>
          ))}
        </select>
        {outputDevices.length === 0 && (
          <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
            Браузер не показывает список колонок (Firefox / Safari ограничивают). Используется системное устройство.
          </p>
        )}

        <label className="block text-xs uppercase tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>
          Голос клиента
        </label>
        <select
          value={props.ttsVoice || "default"}
          onChange={(e) => props.onChangeTtsVoice(e.target.value)}
          className="w-full rounded-lg px-3 py-2 text-sm outline-none mb-3"
          style={{
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
            color: "var(--text-primary)",
          }}
        >
          {TTS_VOICES.map((v) => (
            <option key={v.id} value={v.id}>{v.label}</option>
          ))}
        </select>

        <label className="block text-xs uppercase tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>
          Темп озвучки: {props.ttsRate.toFixed(2)}×
        </label>
        <input
          type="range"
          min={0.5}
          max={1.5}
          step={0.05}
          value={props.ttsRate}
          onChange={(e) => props.onChangeTtsRate(Number(e.target.value))}
          className="w-full mb-3 cursor-pointer accent-current"
          style={{ accentColor: "var(--accent)" }}
          aria-label="Темп озвучки"
        />

        <div className="flex items-center gap-2">
          {!previewing ? (
            <motion.button
              type="button"
              onClick={playPreview}
              whileTap={{ scale: 0.96 }}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
              style={{ background: "var(--accent-muted)", color: "var(--accent)", border: "1px solid var(--accent)" }}
            >
              <Waveform weight="duotone" size={12} /> Предпрослушать
            </motion.button>
          ) : (
            <motion.button
              type="button"
              onClick={stopPreview}
              whileTap={{ scale: 0.96 }}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
              style={{ background: "var(--danger-muted)", color: "var(--danger)", border: "1px solid var(--danger)" }}
            >
              <Stop weight="fill" size={12} /> Стоп
            </motion.button>
          )}
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            Тест на браузерной озвучке. На звонке используется ElevenLabs.
          </span>
        </div>
      </div>
    </div>
  );
}

function ToggleRow({ label, hint, on, onChange }: { label: string; hint: string; on: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      onClick={onChange}
      className="flex items-start justify-between gap-2 rounded-lg p-2.5 text-left transition-colors"
      style={{
        background: on ? "var(--accent-muted)" : "var(--input-bg)",
        border: `1px solid ${on ? "var(--accent)" : "var(--border-color)"}`,
      }}
    >
      <div className="min-w-0">
        <div className="text-xs font-medium" style={{ color: on ? "var(--accent)" : "var(--text-primary)" }}>
          {label}
        </div>
        <div className="text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>
          {hint}
        </div>
      </div>
      <div
        className="shrink-0 w-3.5 h-3.5 rounded-full mt-0.5"
        style={{
          background: on ? "var(--accent)" : "var(--border-color)",
          boxShadow: on ? "0 0 6px var(--accent)" : "none",
        }}
      />
    </button>
  );
}

export type { AudioDevicesPanelProps };
