"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";

/* ── Types ────────────────────────────────────────────────────────── */

interface LinkStatus {
  linked: boolean;
  chat_id: number | null;
}

interface LinkCode {
  code: string;
  bot_username: string;
  expires_seconds: number;
}

/* ── Component ────────────────────────────────────────────────────── */

export default function TelegramLinkWidget() {
  const [status, setStatus] = useState<LinkStatus | null>(null);
  const [linkCode, setLinkCode] = useState<LinkCode | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [unlinking, setUnlinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const data = await api.get<LinkStatus>("/integrations/telegram/status");
      setStatus(data);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleGenerateCode = async () => {
    setGenerating(true);
    setError(null);
    try {
      const data = await api.post<LinkCode>("/integrations/telegram/link", {});
      setLinkCode(data);
    } catch {
      setError("Не удалось получить код");
    } finally {
      setGenerating(false);
    }
  };

  const handleUnlink = async () => {
    setUnlinking(true);
    try {
      await api.delete("/integrations/telegram/link");
      setStatus({ linked: false, chat_id: null });
      setLinkCode(null);
    } catch {
      setError("Не удалось отвязать");
    } finally {
      setUnlinking(false);
    }
  };

  if (loading) return null;
  if (!status) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-xl overflow-hidden"
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--input-bg)",
      }}
    >
      <div className="px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span style={{ fontSize: 20 }}>🤖</span>
            <div>
              <h3
                className="font-pixel text-sm uppercase tracking-wider"
                style={{ color: "var(--text-primary)" }}
              >
                Telegram Bot
              </h3>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                {status.linked
                  ? "Привязан — получаешь разбор ошибок после сессий"
                  : "Привяжи аккаунт для уведомлений"}
              </p>
            </div>
          </div>

          {status.linked ? (
            <div className="flex items-center gap-2">
              <span
                className="text-xs px-2 py-1 rounded-full font-medium"
                style={{
                  background: "color-mix(in srgb, var(--success) 15%, transparent)",
                  color: "var(--success)",
                }}
              >
                Привязан
              </span>
              <button
                onClick={handleUnlink}
                disabled={unlinking}
                className="text-xs px-2 py-1 rounded transition-colors"
                style={{ color: "var(--text-muted)" }}
              >
                {unlinking ? "..." : "Отвязать"}
              </button>
            </div>
          ) : (
            <motion.button
              onClick={handleGenerateCode}
              disabled={generating}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
              style={{ background: "var(--accent)", color: "white" }}
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
            >
              {generating ? "..." : "Привязать"}
            </motion.button>
          )}
        </div>

        {/* Link code display */}
        <AnimatePresence>
          {linkCode && !status.linked && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div
                className="mt-3 p-3 rounded-lg text-center"
                style={{ background: "var(--input-bg)" }}
              >
                <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>
                  1. Открой бота в Telegram:
                </p>
                <a
                  href={`https://t.me/${linkCode.bot_username}?start=${linkCode.code}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block px-4 py-2 rounded-lg text-sm font-medium mb-2"
                  style={{ background: "#0088cc", color: "white" }}
                >
                  @{linkCode.bot_username}
                </a>
                <p className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                  2. Или отправь боту код:
                </p>
                <span
                  className="inline-block font-mono text-lg font-bold px-4 py-1 rounded"
                  style={{
                    background: "var(--card-bg)",
                    color: "var(--accent)",
                    letterSpacing: "0.2em",
                  }}
                >
                  {linkCode.code}
                </span>
                <p className="text-[10px] mt-2" style={{ color: "var(--text-muted)" }}>
                  Код действует 5 минут
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {error && (
          <p className="text-xs mt-2" style={{ color: "var(--danger, #ef4444)" }}>
            {error}
          </p>
        )}
      </div>
    </motion.div>
  );
}
