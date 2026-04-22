"use client";

/**
 * IncomingCallScreen (2026-04-23, Sprint 5 / Zone 2 of plan moonlit-baking-crane.md)
 *
 * iPhone-style «входящий звонок» screen with full client context on the
 * phone UI. Replaces the old inline accept-gate in call/page.tsx (which
 * had only «📞 Входящий звонок» + one Accept button without any client
 * data, no Decline, no loop ringback).
 *
 * Key UX goals:
 *   - User immediately sees WHO is calling (name, age, city, profession,
 *     lead source, debt amount) before accepting — sells «CRM-driven
 *     training» positioning.
 *   - Two large buttons: Accept (green gradient, pulse) / Decline (red
 *     outline). Real phone-call feel.
 *   - Framer Motion animations (outer ring pulse, breathing scale, text
 *     stagger) make the screen feel alive while waiting for client_card
 *     to arrive via WS.
 *   - clientCard prop is nullable — component renders minimal state and
 *     fills in details when parent gets WS session.started event.
 *
 * The component itself is presentational — all audio (loop ringback),
 * sessionStorage persist, WS gate, POST /decline are orchestrated by
 * the parent (call/page.tsx).
 */

import { useMemo } from "react";
import { motion } from "framer-motion";
import { Phone, PhoneOff, MapPin, Briefcase, Wallet } from "lucide-react";
import type { EmotionState } from "@/types";
import { EMOTION_MAP } from "@/types";
import type { ClientCardData } from "@/components/training/ClientCard";

const SCENE_LABEL: Record<string, string> = {
  office: "Звонит из офиса",
  street: "На улице",
  children: "Дома с семьёй",
  tv: "Дома, рядом телевизор",
  none: "Входящий звонок",
};

const LEAD_SOURCE_LABELS: Record<string, string> = {
  cold_base: "Холодная база",
  website_form: "Заявка с сайта",
  referral: "Рекомендация",
  social_media: "Соцсети",
  partner: "Партнёр",
  incoming: "Входящий",
  repeat_call: "Повторный звонок",
};

const fmt = new Intl.NumberFormat("ru-RU");

function formatDebt(amount: number | undefined): string | null {
  if (!amount || amount <= 0) return null;
  if (amount >= 1_000_000) {
    return `${(amount / 1_000_000).toFixed(1).replace(/\.0$/, "")} млн ₽`;
  }
  if (amount >= 1_000) {
    return `${Math.round(amount / 1_000)} тыс ₽`;
  }
  return `${fmt.format(amount)} ₽`;
}

export interface IncomingCallScreenProps {
  characterName: string;
  /** Initial emotion from WS session.started — drives avatar ring color. */
  emotion?: EmotionState;
  /** Scene id from session.custom_params.bg_noise — drives the
   *  «Звонит из офиса» hint at the top. */
  sceneId?: string | null;
  /** Full CRM card. Null until WS session.started arrives — component
   *  renders minimal state and fills on update. */
  clientCard?: ClientCardData | null;
  /** Called on Accept click. Parent runs 3-vector audio unlock, stops the
   *  loop ringback, then flips its own state (callAccepted=true). */
  onAccept: () => void;
  /** Called on Decline click. Parent POST /decline, then router.replace. */
  onDecline: () => void;
  /** True once user has clicked Accept but before routing transitions
   *  finish — disables both buttons, dims Accept to «Соединяем...». */
  accepting?: boolean;
  /** True once user has clicked Decline — disables both buttons. */
  declining?: boolean;
}

export default function IncomingCallScreen({
  characterName,
  emotion,
  sceneId,
  clientCard,
  onAccept,
  onDecline,
  accepting = false,
  declining = false,
}: IncomingCallScreenProps) {
  const sceneKey = sceneId && sceneId in SCENE_LABEL ? sceneId : "none";
  const sceneLabel = SCENE_LABEL[sceneKey];
  const ec = EMOTION_MAP[emotion || "cold"] || EMOTION_MAP.cold;

  // Derived client info. All fields can be missing if clientCard hasn't
  // arrived yet — use graceful fallbacks so the minimal render still
  // looks complete.
  const initial = useMemo(
    () => (characterName || clientCard?.full_name || "К").charAt(0).toUpperCase(),
    [characterName, clientCard],
  );
  const displayName = clientCard?.full_name || characterName || "Клиент";
  const ageCity = [
    clientCard?.age ? `${clientCard.age}` : null,
    clientCard?.city || null,
  ]
    .filter(Boolean)
    .join(", ");
  const profession = clientCard?.profession || null;
  const leadSource = clientCard?.lead_source_label
    || (clientCard?.lead_source && LEAD_SOURCE_LABELS[clientCard.lead_source])
    || null;
  const debtStr = formatDebt(clientCard?.total_debt);

  const busy = accepting || declining;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="fixed inset-0 z-50 flex flex-col items-center overflow-y-auto text-white"
      style={{
        background:
          "radial-gradient(ellipse at center, #2a1a4a 0%, #14091e 55%, #06030c 100%)",
      }}
    >
      {/* Top strip — "Входящий звонок" + scene hint */}
      <motion.div
        initial={{ y: -12, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1, duration: 0.4 }}
        className="flex w-full items-center justify-between px-6 pt-8 md:pt-10"
      >
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">
          Входящий звонок
        </span>
        <span className="text-xs font-medium text-white/45">{sceneLabel}</span>
      </motion.div>

      {/* Flex spacer + avatar block */}
      <div className="flex flex-1 flex-col items-center justify-center px-6 pt-6 md:pt-0">
        {/* Avatar + outer pulse ring */}
        <motion.div
          className="relative flex items-center justify-center"
          animate={{ scale: [1, 1.04, 1] }}
          transition={{
            duration: 3,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        >
          <motion.div
            aria-hidden
            className="absolute rounded-full"
            animate={{
              scale: [1, 1.12, 1],
              opacity: [0.4, 0.7, 0.4],
            }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            style={{
              width: 280,
              height: 280,
              border: `2px solid ${ec.color}`,
              boxShadow: `0 0 60px ${ec.glow}`,
            }}
          />
          <div
            className="flex items-center justify-center rounded-full text-[88px] font-bold leading-none"
            style={{
              width: 220,
              height: 220,
              background: "rgba(255,255,255,0.04)",
              border: `3px solid ${ec.color}`,
              boxShadow: `inset 0 0 30px ${ec.glow}`,
              color: ec.color,
              letterSpacing: "-0.02em",
            }}
            aria-hidden
          >
            {initial}
          </div>
        </motion.div>

        {/* Name */}
        <motion.h1
          initial={{ y: 12, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.25, duration: 0.35 }}
          className="mt-8 text-center text-3xl font-semibold tracking-tight"
        >
          {displayName}
        </motion.h1>

        {/* Age + city */}
        {ageCity && (
          <motion.div
            initial={{ y: 8, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.33, duration: 0.35 }}
            className="mt-2 flex items-center gap-1.5 text-sm text-white/70"
          >
            <MapPin size={14} className="opacity-60" aria-hidden />
            <span>{ageCity}</span>
          </motion.div>
        )}

        {/* Profession */}
        {profession && (
          <motion.div
            initial={{ y: 8, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.41, duration: 0.35 }}
            className="mt-1 flex items-center gap-1.5 text-sm text-white/70"
          >
            <Briefcase size={14} className="opacity-60" aria-hidden />
            <span>{profession}</span>
          </motion.div>
        )}

        {/* Lead-source badge + debt chip */}
        <motion.div
          initial={{ y: 8, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.49, duration: 0.35 }}
          className="mt-5 flex flex-wrap items-center justify-center gap-2"
        >
          {leadSource && (
            <span
              className="inline-flex items-center rounded-full px-3 py-1 text-[11px] font-medium uppercase tracking-wider"
              style={{
                background: "rgba(120,92,220,0.18)",
                color: "rgba(200,180,255,0.95)",
                border: "1px solid rgba(120,92,220,0.4)",
              }}
            >
              {leadSource}
            </span>
          )}
          {debtStr && (
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold"
              style={{
                background: "rgba(255,200,100,0.12)",
                color: "rgba(255,220,140,0.95)",
                border: "1px solid rgba(255,200,100,0.28)",
              }}
            >
              <Wallet size={11} className="opacity-80" aria-hidden />
              Долг: {debtStr}
            </span>
          )}
        </motion.div>

        {/* Subtle scene hint when clientCard is still null */}
        {!clientCard && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.55 }}
            transition={{ delay: 0.6 }}
            className="mt-4 text-xs text-white/45"
          >
            Подключаем детали клиента…
          </motion.div>
        )}
      </div>

      {/* Action row — Decline + Accept */}
      <motion.div
        initial={{ y: 16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.55, duration: 0.4 }}
        className="w-full pb-10 md:pb-14"
      >
        <div className="mx-auto flex max-w-md items-center justify-around gap-6 px-6 md:gap-10">
          {/* Decline (red outline) */}
          <button
            type="button"
            onClick={busy ? undefined : onDecline}
            disabled={busy}
            aria-label="Отклонить звонок"
            className="group flex flex-col items-center gap-2 transition disabled:cursor-wait"
          >
            <motion.span
              whileTap={busy ? undefined : { scale: 0.92 }}
              whileHover={busy ? undefined : { scale: 1.04 }}
              className="flex h-18 w-18 items-center justify-center rounded-full md:h-20 md:w-20"
              style={{
                width: 72,
                height: 72,
                background: declining
                  ? "rgba(255,59,89,0.85)"
                  : "rgba(255,59,89,0.08)",
                border: "2px solid rgba(255,59,89,0.65)",
                color: declining ? "#fff" : "rgba(255,100,125,0.95)",
                boxShadow: "inset 0 0 0 1px rgba(255,59,89,0.15)",
              }}
            >
              <PhoneOff size={28} />
            </motion.span>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-red-300/90">
              {declining ? "Отменяем…" : "Отклонить"}
            </span>
          </button>

          {/* Accept (green gradient, pulsing glow) */}
          <button
            type="button"
            onClick={busy ? undefined : onAccept}
            disabled={busy}
            aria-label="Принять звонок"
            className="group flex flex-col items-center gap-2 transition disabled:cursor-wait"
          >
            <motion.span
              whileTap={busy ? undefined : { scale: 0.92 }}
              whileHover={busy ? undefined : { scale: 1.04 }}
              animate={
                accepting
                  ? { scale: 0.96 }
                  : busy
                  ? undefined
                  : {
                      boxShadow: [
                        "0 6px 24px rgba(61,220,132,0.35)",
                        "0 6px 36px rgba(61,220,132,0.75)",
                        "0 6px 24px rgba(61,220,132,0.35)",
                      ],
                    }
              }
              transition={
                busy
                  ? undefined
                  : {
                      duration: 1.6,
                      repeat: Infinity,
                      ease: "easeInOut",
                    }
              }
              className="flex items-center justify-center rounded-full"
              style={{
                width: 72,
                height: 72,
                background:
                  "linear-gradient(135deg, rgba(61,220,132,0.95) 0%, rgba(40,175,100,0.95) 100%)",
                color: "#062a13",
              }}
            >
              {accepting ? (
                <motion.span
                  animate={{ rotate: 360 }}
                  transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }}
                  className="inline-block h-5 w-5 rounded-full border-2 border-[#062a13]/30 border-t-[#062a13]"
                />
              ) : (
                <Phone size={28} />
              )}
            </motion.span>
            <span
              className="text-[11px] font-semibold uppercase tracking-wider"
              style={{ color: "rgba(180,255,210,0.95)" }}
            >
              {accepting ? "Соединяем…" : "Принять"}
            </span>
          </button>
        </div>

        <div className="mx-auto mt-5 max-w-xs text-center text-[11px] text-white/40">
          Нажмите «Принять» чтобы подключить звук —
          <br />
          браузер требует жест пользователя
        </div>
      </motion.div>
    </motion.div>
  );
}
