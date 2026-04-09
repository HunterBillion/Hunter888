"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, MicOff, CheckCircle2, AlertTriangle, Volume2 } from "lucide-react";

type MicCheckStatus = "idle" | "checking" | "success" | "denied" | "error";

interface MicCheckProps {
  onComplete: (micAvailable: boolean) => void;
  onSkip: () => void;
}

export function MicCheck({ onComplete, onSkip }: MicCheckProps) {
  const [status, setStatus] = useState<MicCheckStatus>("idle");
  const [level, setLevel] = useState(0);
  const streamRef = useRef<MediaStream | null>(null);
  const animRef = useRef(0);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const contextRef = useRef<AudioContext | null>(null);

  const cleanup = useCallback(() => {
    cancelAnimationFrame(animRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    contextRef.current?.close().catch(() => {});
    contextRef.current = null;
    analyserRef.current = null;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const checkMic = async () => {
    setStatus("checking");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;

      const ctx = new AudioContext();
      contextRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);
      analyserRef.current = analyser;

      setStatus("success");

      // Monitor level for visual feedback
      const monitor = () => {
        if (!analyserRef.current) return;
        const data = new Uint8Array(analyserRef.current.frequencyBinCount);
        analyserRef.current.getByteFrequencyData(data);
        const avg = data.reduce((s, v) => s + v, 0) / data.length;
        setLevel(Math.min(100, Math.round((avg / 255) * 100 * 2)));
        animRef.current = requestAnimationFrame(monitor);
      };
      animRef.current = requestAnimationFrame(monitor);
    } catch (err) {
      if (err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "PermissionDeniedError")) {
        setStatus("denied");
      } else {
        setStatus("error");
      }
    }
  };

  const proceed = () => {
    cleanup();
    onComplete(status === "success");
  };

  const skip = () => {
    cleanup();
    onSkip();
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass-panel max-w-md mx-auto p-8 text-center"
    >
      <div
        className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl"
        style={{
          background: status === "success" ? "rgba(0,255,102,0.1)" : status === "denied" || status === "error" ? "rgba(255,51,51,0.1)" : "var(--accent-muted)",
          border: `2px solid ${status === "success" ? "var(--success)" : status === "denied" || status === "error" ? "var(--danger)" : "var(--accent)"}`,
        }}
      >
        {status === "success" ? (
          <CheckCircle2 size={36} style={{ color: "var(--success)" }} />
        ) : status === "denied" || status === "error" ? (
          <MicOff size={36} style={{ color: "var(--danger)" }} />
        ) : (
          <Mic size={36} style={{ color: "var(--accent)" }} />
        )}
      </div>

      <h2 className="font-display text-xl font-bold tracking-wider mb-2" style={{ color: "var(--text-primary)" }}>
        {status === "idle" && "ПРОВЕРКА МИКРОФОНА"}
        {status === "checking" && "ПОДКЛЮЧЕНИЕ..."}
        {status === "success" && "МИКРОФОН ГОТОВ"}
        {status === "denied" && "ДОСТУП ЗАПРЕЩЁН"}
        {status === "error" && "ОШИБКА МИКРОФОНА"}
      </h2>

      <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
        {status === "idle" && "Для голосовой тренировки нужен доступ к микрофону"}
        {status === "checking" && "Разрешите доступ к микрофону в браузере"}
        {status === "success" && "Говорите — индикатор должен реагировать на голос"}
        {status === "denied" && "Разрешите доступ в настройках браузера или используйте текстовый режим"}
        {status === "error" && "Не удалось подключить микрофон. Проверьте устройство."}
      </p>

      {/* Audio level bar */}
      {status === "success" && (
        <div className="mb-6">
          <div className="flex items-center gap-2 justify-center mb-2">
            <Volume2 size={14} style={{ color: "var(--accent)" }} />
            <span className="font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>УРОВЕНЬ СИГНАЛА</span>
          </div>
          <div className="h-3 rounded-full overflow-hidden mx-auto max-w-[200px]" style={{ background: "var(--input-bg)" }}>
            <motion.div
              className="h-full rounded-full"
              style={{ background: level > 30 ? "var(--success)" : "var(--accent)", boxShadow: level > 30 ? "0 0 8px rgba(0,255,102,0.5)" : "none" }}
              animate={{ width: `${Math.max(5, level)}%` }}
              transition={{ duration: 0.1 }}
            />
          </div>
        </div>
      )}

      <div className="flex gap-3 justify-center">
        {status === "idle" && (
          <>
            <motion.button onClick={checkMic} className="btn-neon flex items-center gap-2" whileTap={{ scale: 0.97 }}>
              <Mic size={16} /> Проверить микрофон
            </motion.button>
            <motion.button onClick={skip} className="btn-neon" whileTap={{ scale: 0.97 }}>
              Текстовый режим
            </motion.button>
          </>
        )}
        {status === "success" && (
          <motion.button onClick={proceed} className="btn-neon flex items-center gap-2" whileTap={{ scale: 0.97 }}>
            <CheckCircle2 size={16} /> Начать тренировку
          </motion.button>
        )}
        {(status === "denied" || status === "error") && (
          <>
            <motion.button onClick={checkMic} className="btn-neon flex items-center gap-2" whileTap={{ scale: 0.97 }}>
              <AlertTriangle size={14} /> Повторить
            </motion.button>
            <motion.button onClick={skip} className="btn-neon" whileTap={{ scale: 0.97 }}>
              Текстовый режим
            </motion.button>
          </>
        )}
      </div>
    </motion.div>
  );
}
