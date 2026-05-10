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

  /*
   * 2026-05-10 (pixel redesign): iPhone-style rounded-full → square pixel.
   * Сохранены ВСЕ анимации (pulse outer ring, breathing scale, stagger
   * entry), ВСЯ логика accepting/declining/busy, callbacks (onAccept,
   * onDecline). Поменял только rounded → rounded-sm + 3px solid borders,
   * font-display/sans → font-pixel uppercase tracking-widest, размер
   * шрифтов поднят до ≥14px по консистентности с остальным сайтом.
   *
   * Phase A (2026-05-08): exit animation off `busy` сохранена — parent
   * defer'ит setCallAccepted на 220ms, экран успевает fade+shrink.
   */
  return (
    <motion.div
      initial={{ opacity: 0, scale: 1 }}
      animate={{
        opacity: busy ? 0 : 1,
        scale: busy ? 0.96 : 1,
      }}
      transition={{ duration: busy ? 0.2 : 0.3, ease: "easeOut" }}
      className="fixed inset-0 z-50 flex flex-col items-center overflow-y-auto"
      style={{
        background:
          "radial-gradient(ellipse at center, rgba(42,26,74,0.96) 0%, rgba(20,9,30,0.98) 55%, rgba(6,3,12,1) 100%)",
        color: "var(--text-primary)",
      }}
    >
      {/* Top strip — «▰ ВХОДЯЩИЙ ЗВОНОК ▰» + scene hint, font-pixel 14px */}
      <motion.div
        initial={{ y: -12, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1, duration: 0.4 }}
        className="flex w-full items-center justify-between px-6 pt-8 md:pt-10"
      >
        <span
          className="font-pixel uppercase tracking-widest"
          style={{ color: "rgba(255,255,255,0.6)", fontSize: 14, letterSpacing: "0.22em" }}
        >
          ▰ ВХОДЯЩИЙ ЗВОНОК ▰
        </span>
        <span
          className="font-pixel uppercase tracking-widest"
          style={{ color: "rgba(255,255,255,0.5)", fontSize: 14 }}
        >
          {sceneLabel}
        </span>
      </motion.div>

      {/* Flex spacer + avatar block */}
      <div className="flex flex-1 flex-col items-center justify-center px-6 pt-6 md:pt-0">
        {/* Avatar + outer pulse — square pixel вместо rounded-full */}
        <motion.div
          className="relative flex items-center justify-center"
          animate={{ scale: [1, 1.04, 1] }}
          transition={{
            duration: 3,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        >
          {/* Outer pulse ring — square pixel */}
          <motion.div
            aria-hidden
            className="absolute rounded-sm"
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
          {/* Inner pulse — даём двойной ring для аркадного «таргета» */}
          <motion.div
            aria-hidden
            className="absolute rounded-sm"
            animate={{
              scale: [1, 1.06, 1],
              opacity: [0.25, 0.55, 0.25],
            }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
            style={{
              width: 250,
              height: 250,
              border: `1px dashed ${ec.color}`,
            }}
          />
          {/* Avatar square с пиксельными инициалами */}
          <div
            className="flex items-center justify-center rounded-sm font-pixel"
            style={{
              width: 220,
              height: 220,
              background: "rgba(255,255,255,0.04)",
              border: `4px solid ${ec.color}`,
              boxShadow: `inset 0 0 30px ${ec.glow}, 0 0 24px ${ec.glow}`,
              color: ec.color,
              fontSize: 92,
              lineHeight: 1,
              letterSpacing: "0.02em",
              textShadow: `0 0 16px ${ec.glow}`,
            }}
            aria-hidden
          >
            {initial}
          </div>
        </motion.div>

        {/* Name — font-pixel large */}
        <motion.h1
          initial={{ y: 12, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.25, duration: 0.35 }}
          className="mt-8 text-center font-pixel"
          style={{
            fontSize: "clamp(28px, 5vw, 38px)",
            letterSpacing: "0.04em",
            textShadow: "0 0 14px rgba(167,139,250,0.4)",
          }}
        >
          {displayName}
        </motion.h1>

        {/* Age + city — font-pixel 14px */}
        {ageCity && (
          <motion.div
            initial={{ y: 8, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.33, duration: 0.35 }}
            className="mt-3 flex items-center gap-2 font-pixel uppercase tracking-widest"
            style={{ color: "rgba(255,255,255,0.7)", fontSize: 14, letterSpacing: "0.18em" }}
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
            className="mt-1.5 flex items-center gap-2 font-pixel uppercase tracking-widest"
            style={{ color: "rgba(255,255,255,0.7)", fontSize: 14, letterSpacing: "0.18em" }}
          >
            <Briefcase size={14} className="opacity-60" aria-hidden />
            <span>{profession}</span>
          </motion.div>
        )}

        {/* Lead-source badge + debt chip — square pixel 2px solid */}
        <motion.div
          initial={{ y: 8, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.49, duration: 0.35 }}
          className="mt-5 flex flex-wrap items-center justify-center gap-2"
        >
          {leadSource && (
            <span
              className="inline-flex items-center rounded-sm px-3 py-1.5 font-pixel uppercase tracking-widest"
              style={{
                background: "rgba(167,139,250,0.18)",
                color: "rgba(220,210,255,0.95)",
                border: "2px solid rgba(167,139,250,0.5)",
                fontSize: 14,
                letterSpacing: "0.18em",
              }}
            >
              {leadSource}
            </span>
          )}
          {debtStr && (
            <span
              className="inline-flex items-center gap-1.5 rounded-sm px-3 py-1.5 font-pixel uppercase tracking-widest"
              style={{
                background: "rgba(255,200,100,0.14)",
                color: "rgba(255,220,140,0.98)",
                border: "2px solid rgba(255,200,100,0.45)",
                fontSize: 14,
                letterSpacing: "0.18em",
              }}
            >
              <Wallet size={13} className="opacity-90" aria-hidden />
              ДОЛГ: {debtStr}
            </span>
          )}
        </motion.div>

        {/* Subtle scene hint when clientCard is still null */}
        {!clientCard && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.55 }}
            transition={{ delay: 0.6 }}
            className="mt-4 font-pixel uppercase tracking-widest"
            style={{ color: "rgba(255,255,255,0.45)", fontSize: 14 }}
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
          {/* Decline — square pixel 3px solid red */}
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
              className="flex items-center justify-center rounded-sm"
              style={{
                width: 76,
                height: 76,
                background: declining
                  ? "rgba(248,113,113,0.92)"
                  : "rgba(248,113,113,0.12)",
                border: "3px solid #f87171",
                color: declining ? "#0b0b14" : "#fca5a5",
                boxShadow: declining
                  ? "0 0 22px rgba(248,113,113,0.7)"
                  : "0 0 14px rgba(248,113,113,0.35)",
              }}
            >
              <PhoneOff size={30} strokeWidth={2.4} />
            </motion.span>
            <span
              className="font-pixel uppercase tracking-widest"
              style={{ color: "#fca5a5", fontSize: 14, letterSpacing: "0.22em" }}
            >
              {declining ? "ОТМЕНЯЕМ…" : "ОТКЛОНИТЬ"}
            </span>
          </button>

          {/* Accept — square pixel green с pulsing glow */}
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
                        "0 0 18px rgba(74,222,128,0.45)",
                        "0 0 38px rgba(74,222,128,0.85)",
                        "0 0 18px rgba(74,222,128,0.45)",
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
              className="flex items-center justify-center rounded-sm"
              style={{
                width: 76,
                height: 76,
                background:
                  "linear-gradient(135deg, #4ade80 0%, #22c55e 100%)",
                border: "3px solid #062a13",
                color: "#062a13",
              }}
            >
              {accepting ? (
                <motion.span
                  animate={{ rotate: 360 }}
                  transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }}
                  className="inline-block rounded-sm border-[3px] border-[#062a13]/30 border-t-[#062a13]"
                  style={{ width: 22, height: 22 }}
                />
              ) : (
                <Phone size={30} strokeWidth={2.4} />
              )}
            </motion.span>
            <span
              className="font-pixel uppercase tracking-widest"
              style={{ color: "rgba(180,255,210,0.95)", fontSize: 14, letterSpacing: "0.22em" }}
            >
              {accepting ? "СОЕДИНЯЕМ…" : "ПРИНЯТЬ"}
            </span>
          </button>
        </div>

        <div
          className="mx-auto mt-5 max-w-md text-center font-pixel uppercase tracking-widest"
          style={{ color: "rgba(255,255,255,0.4)", fontSize: 14, letterSpacing: "0.18em", lineHeight: 1.4 }}
        >
          Нажмите «Принять» чтобы подключить звук —<br />
          браузер требует жест пользователя
        </div>
      </motion.div>
    </motion.div>
  );
}
