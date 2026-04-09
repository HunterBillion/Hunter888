"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  User,
  Briefcase,
  MapPin,
  Banknote,
  AlertTriangle,
  Shield,
  Mic,
  Keyboard,
  ChevronRight,
  Phone,
} from "lucide-react";
import { EMOTION_MAP, type EmotionState } from "@/types";

interface ClientInfo {
  full_name: string;
  age: number;
  gender: string;
  city: string;
  archetype_code: string;
  total_debt: number;
  creditors: Array<{ name: string; amount: number }>;
  income: number | null;
  income_type: string;
  fears: string[];
  lead_source: string;
  call_history: Array<{ date: string; result: string }>;
  crm_notes: string | null;
  property_list: Array<{ type: string; status: string }>;
  profession?: { name: string; category: string } | null;
}

interface ScenarioInfo {
  title: string;
  description: string;
  scenario_type: string;
  difficulty: number;
  character: {
    name: string;
    description: string;
    initial_emotion: EmotionState;
    difficulty: number;
  } | null;
  script: {
    title: string;
    checkpoints: Array<{ title: string; description: string }>;
  } | null;
}

interface PreSessionBriefProps {
  scenario: ScenarioInfo | null;
  client: ClientInfo | null;
  onStart: (mode: "voice" | "text") => void;
  loading?: boolean;
}

function formatDebt(amount: number): string {
  if (amount >= 1_000_000) return `${(amount / 1_000_000).toFixed(1)}М ₽`;
  if (amount >= 1_000) return `${Math.round(amount / 1_000)}К ₽`;
  return `${amount} ₽`;
}

function difficultyLabel(d: number): { text: string; color: string } {
  if (d <= 3) return { text: "ЛЕГКО", color: "var(--success)" };
  if (d <= 6) return { text: "СРЕДНЕ", color: "var(--warning)" };
  return { text: "СЛОЖНО", color: "var(--danger)" };
}

function scenarioTypeLabel(type: string): string {
  switch (type) {
    case "cold_call": return "ХОЛОДНЫЙ ЗВОНОК";
    case "warm_call": return "ДОЖИМ";
    case "objection_handling": return "ВОЗРАЖЕНИЯ";
    case "consultation": return "КОНСУЛЬТАЦИЯ";
    default: return type.toUpperCase();
  }
}

export function PreSessionBrief({ scenario, client, onStart, loading }: PreSessionBriefProps) {
  const [countdown, setCountdown] = useState<number | null>(null);
  const [selectedMode, setSelectedMode] = useState<"voice" | "text" | null>(null);

  const handleStart = useCallback((mode: "voice" | "text") => {
    setSelectedMode(mode);
    setCountdown(3);
  }, []);

  useEffect(() => {
    if (countdown === null) return;
    if (countdown === 0) {
      onStart(selectedMode || "voice");
      return;
    }
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown, onStart, selectedMode]);

  if (loading || !scenario) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-transparent" style={{ borderTopColor: "var(--accent)" }} />
      </div>
    );
  }

  const diff = difficultyLabel(scenario.difficulty);
  const character = scenario.character;
  const emotionConfig = character ? EMOTION_MAP[character.initial_emotion] || EMOTION_MAP.cold : EMOTION_MAP.cold;

  // Countdown overlay
  if (countdown !== null) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={countdown}
            initial={{ scale: 2, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.5, opacity: 0 }}
            transition={{ duration: 0.4 }}
            className="text-center"
          >
            {countdown > 0 ? (
              <span className="font-display text-[120px] font-bold" style={{ color: "var(--accent)", textShadow: `0 0 40px ${emotionConfig.glow}` }}>
                {countdown}
              </span>
            ) : (
              <span className="font-display text-4xl font-bold tracking-[0.3em]" style={{ color: "var(--success)" }}>
                GO
              </span>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: "var(--bg-primary)" }}>

      <div className="flex-1 overflow-y-auto p-6 md:p-10 z-10">
        <div className="mx-auto max-w-4xl">
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center gap-3 mb-2">
              <Phone size={18} style={{ color: "var(--accent)" }} />
              <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                {scenarioTypeLabel(scenario.scenario_type)}
              </span>
              <span className="font-mono text-xs px-2 py-0.5 rounded-full" style={{ background: `color-mix(in srgb, ${diff.color} 8%, transparent)`, color: diff.color }}>
                {diff.text} ({scenario.difficulty}/10)
              </span>
            </div>
            <h1 className="font-display text-2xl md:text-3xl font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
              {scenario.title}
            </h1>
            <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {scenario.description}
            </p>
          </motion.div>

          <div className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: Client CRM Card */}
            {client && (
              <motion.div
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.1 }}
                className="glass-panel p-6 relative overflow-hidden"
                style={{ borderLeft: `3px solid ${emotionConfig.color}` }}
              >
                <div className="absolute -top-10 -right-10 w-32 h-32 rounded-full opacity-10 blur-[60px]" style={{ background: emotionConfig.color }} />

                <h2 className="font-display text-sm tracking-widest mb-4 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
                  <User size={14} /> CRM-КАРТОЧКА КЛИЕНТА
                </h2>

                {/* Identity */}
                <div className="mb-4">
                  <div className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>
                    {client.full_name}
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
                    <span>{client.age} лет</span>
                    {client.city && <span className="flex items-center gap-1"><MapPin size={10} />{client.city}</span>}
                    {client.profession && <span className="flex items-center gap-1"><Briefcase size={10} />{client.profession.name}</span>}
                  </div>
                </div>

                {/* Debt */}
                <div className="mb-4 p-3 rounded-lg" style={{ background: "var(--input-bg)" }}>
                  <div className="flex items-center gap-2 mb-2">
                    <Banknote size={14} style={{ color: "var(--danger)" }} />
                    <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>ДОЛГИ</span>
                  </div>
                  <div className="font-display text-2xl font-bold" style={{ color: "var(--danger)" }}>
                    {formatDebt(client.total_debt)}
                  </div>
                  {client.creditors.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {client.creditors.slice(0, 4).map((c, i) => (
                        <div key={i} className="flex justify-between text-xs" style={{ color: "var(--text-secondary)" }}>
                          <span>{c.name}</span>
                          <span className="font-mono">{formatDebt(c.amount)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Fears */}
                {client.fears.length > 0 && (
                  <div className="mb-4">
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle size={14} style={{ color: "var(--warning)" }} />
                      <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>СТРАХИ</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {client.fears.slice(0, 5).map((fear, i) => (
                        <span key={i} className="rounded-full px-2.5 py-0.5 text-xs" style={{ background: "rgba(212,168,75,0.08)", color: "var(--warning)", border: "1px solid rgba(212,168,75,0.15)" }}>
                          {fear}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* CRM Notes */}
                {client.crm_notes && (
                  <div className="p-3 rounded-lg text-xs italic" style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}>
                    "{client.crm_notes}"
                  </div>
                )}

                {/* Initial state */}
                <div className="mt-4 flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ background: emotionConfig.color, boxShadow: `0 0 6px ${emotionConfig.glow}` }} />
                  <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: emotionConfig.color }}>
                    НАЧАЛЬНОЕ СОСТОЯНИЕ: {emotionConfig.label}
                  </span>
                </div>
              </motion.div>
            )}

            {/* Right: Script + Focus */}
            <motion.div
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
              className="space-y-6"
            >
              {/* Script checkpoints */}
              {scenario.script && (
                <div className="glass-panel p-6">
                  <h2 className="font-display text-sm tracking-widest mb-4 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
                    <Shield size={14} style={{ color: "var(--accent)" }} /> ПЛАН РАЗГОВОРА
                  </h2>
                  <div className="space-y-2">
                    {scenario.script.checkpoints.map((cp, i) => (
                      <div key={i} className="flex items-start gap-3">
                        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-xs font-bold" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
                          {i + 1}
                        </div>
                        <div>
                          <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{cp.title}</div>
                          <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{cp.description}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Character info */}
              {character && (
                <div className="glass-panel p-6">
                  <h2 className="font-display text-sm tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
                    О КЛИЕНТЕ
                  </h2>
                  <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    {character.description}
                  </p>
                </div>
              )}
            </motion.div>
          </div>

          {/* Start buttons */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="mt-8 flex justify-center gap-4 pb-8"
          >
            <motion.button
              onClick={() => handleStart("voice")}
              className="btn-neon flex items-center gap-3 text-lg px-8 py-4"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Mic size={20} />
              Голосовой режим
              <ChevronRight size={18} />
            </motion.button>
            <motion.button
              onClick={() => handleStart("text")}
              className="btn-neon flex items-center gap-3 px-6 py-4"
              whileTap={{ scale: 0.98 }}
            >
              <Keyboard size={18} />
              Текстовый
            </motion.button>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
