"use client";

import Image from "next/image";
import { motion } from "framer-motion";
import {
  Brain,
  Mic,
  Target,
  Shield,
  Swords,
  Trophy,
  Users,
  BookOpen,
  Scale,
  Flame,
  Star,
  TrendingUp,
  AlertTriangle,
  MessageSquare,
} from "lucide-react";
import { PixelGridBackground } from "@/components/landing/PixelGridBackground";

/* ── Key scoring parameters (top 3 shown large) ───────────────────── */
const SCORING_PRIMARY = [
  { name: "Возражения", desc: "Клиент говорит «дорого» или «не сейчас» — как реагируете? Это параметр, который разделяет новичков и профессионалов.", icon: Shield },
  { name: "Ловушки", desc: "15 типов провокаций от ИИ-клиента. Ложные обещания, давление, манипуляции. Попались — штраф.", icon: AlertTriangle, negative: true },
  { name: "Результат", desc: "Назначили встречу? Получили согласие? Закрыли сделку? Единственный параметр, который измеряет итог.", icon: Trophy },
] as const;

const SCORING_SECONDARY = [
  { name: "Скрипт", desc: "Следуете этапам разговора?", icon: Target },
  { name: "Коммуникация", desc: "Эмпатия, вежливость, скорость реакции.", icon: MessageSquare },
  { name: "Ошибки", desc: "Ловим ложные обещания и давление.", icon: AlertTriangle, negative: true },
  { name: "Эмоции", desc: "Работа с тревогой и агрессией клиента.", icon: Brain },
  { name: "Логика диалога", desc: "Последовательность или хаос?", icon: Target },
  { name: "Юр. точность", desc: "Соответствие 127-ФЗ.", icon: Scale },
  { name: "Баланс речи", desc: "Сколько говорите vs слушаете.", icon: Mic },
] as const;

/* ── PvP Ranks ────────────────────────────────────────────────────── */
const PVP_RANKS = [
  { name: "Bronze", divisions: 3, color: "var(--rank-bronze)", pct: "47%", icon: "/pixel/ranks/bronze.png" },
  { name: "Silver", divisions: 3, color: "var(--rank-silver)", pct: "28%", icon: "/pixel/ranks/silver.png" },
  { name: "Gold", divisions: 3, color: "var(--rank-gold)", pct: "15%", icon: "/pixel/ranks/gold.png" },
  { name: "Platinum", divisions: 3, color: "var(--rank-platinum)", pct: "8%", icon: "/pixel/ranks/platinum.png" },
  { name: "Diamond", divisions: 3, color: "var(--rank-diamond)", pct: "2%", icon: "/pixel/ranks/diamond.png" },
] as const;

/* ── Achievement pixel sprites for gamification section ──────────── */
const ACHIEVEMENT_BADGES = [
  { label: "Первый звонок", sprite: "/pixel/achievements/first-call.png" },
  { label: "5 побед подряд", sprite: "/pixel/achievements/streak-7.png" },
  { label: "Gold I", sprite: "/pixel/achievements/pvp-champion.png" },
  { label: "Мастер возражений", sprite: "/pixel/achievements/objection-master.png" },
  { label: "100 тренировок", sprite: "/pixel/achievements/hundred-calls.png" },
] as const;

/* ═══════════════════════════ PAGE ═════════════════════════════════ */
export default function ProductPage() {
  return (
    <div
      className="relative min-h-screen"
      style={{ background: "var(--bg-primary)", paddingTop: "80px" }}
    >
      {/* Canvas pixel grid — full grid + 15% of cells decay ("disappear") */}
      <div className="absolute inset-0 pointer-events-none">
        <PixelGridBackground cellSize={40} pixelSize={8} />
      </div>

      <div className="relative z-10 max-w-6xl mx-auto px-5 sm:px-8 md:px-10">

        {/* ── 1. HERO — asymmetric 60/40 ──────────────────────── */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start py-12 sm:py-20">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7 }}
            className="lg:col-span-7 space-y-6"
          >
            <h1
              className="font-display font-black tracking-tight leading-[1.05]"
              style={{ fontSize: "clamp(2.5rem, 5vw, 4rem)", color: "var(--text-primary)" }}
            >
              Как работает<br />
              <span style={{ color: "var(--text-primary)" }}>X Hunter</span>
            </h1>

            <div className="max-w-xl space-y-4 text-lg sm:text-xl leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              <p>
                <strong className="font-pixel text-2xl" style={{ color: "var(--accent)" }}>Шаг 1:</strong>{" "}
                Менеджер выбирает ситуацию — холодный звонок, жёсткие переговоры, кризис.
              </p>
              <p>
                <strong className="font-pixel text-2xl" style={{ color: "var(--accent)" }}>Шаг 2:</strong>{" "}
                Разговаривает с ИИ, который ведёт себя как настоящий клиент.
              </p>
              <p>
                <strong className="font-pixel text-2xl" style={{ color: "var(--accent)" }}>Шаг 3:</strong>{" "}
                Получает детальный разбор — что сработало, а где потерял клиента.
              </p>
            </div>

            <div className="flex flex-wrap gap-4 pt-3">
              {[
                { icon: Brain, num: "60", text: "реальных сценариев" },
                { icon: Users, num: "100", text: "типов клиентов" },
                { icon: Mic, num: null, text: "Голосовой режим" },
              ].map(({ icon: BadgeIcon, num, text }) => (
                <div
                  key={text}
                  className="pixel-border flex items-center gap-2.5 px-4 py-2.5 text-sm"
                  style={{ background: "var(--bg-panel)", color: "var(--text-secondary)" }}
                >
                  <BadgeIcon size={16} style={{ color: "var(--text-muted)" }} />
                  {num ? (
                    <span><strong className="font-pixel text-lg" style={{ color: "var(--text-primary)" }}>{num}</strong> {text}</span>
                  ) : (
                    <span>{text}</span>
                  )}
                </div>
              ))}
            </div>
          </motion.div>

          {/* Image slot */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="lg:col-span-5"
          >
            <div
              className="rounded-xl overflow-hidden aspect-square relative"
              style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
            >
              <img
                src="/landing/neural-matrix.jpg"
                alt="Визуализация архитектуры ИИ-скоринга X Hunter"
                className="w-full h-full object-cover"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                  (e.target as HTMLImageElement).parentElement!.style.background = "linear-gradient(135deg, var(--bg-tertiary) 0%, var(--accent-muted) 40%, var(--bg-tertiary) 100%)";
                }}
              />
              <div className="absolute inset-0 pointer-events-none" style={{ background: "linear-gradient(to top, var(--bg-primary) 0%, transparent 40%)" }} />
            </div>
          </motion.div>
        </section>

        {/* ── 2. ANCHOR STAT — full-width, typographic contrast ── */}
        <div className="pixel-divider" />
        <motion.section
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-center py-16 sm:py-24"
        >
          <p className="font-pixel text-lg tracking-widest uppercase mb-4" style={{ color: "var(--text-muted)" }}>
            По данным внутреннего тестирования
          </p>
          <div className="font-pixel pixel-glow leading-none" style={{ fontSize: "clamp(5rem, 14vw, 10rem)", color: "var(--text-primary)" }}>
            7 <span className="text-4xl sm:text-6xl" style={{ color: "var(--text-muted)" }}>из</span> 10
          </div>
          <p
            className="mt-6 text-xl sm:text-2xl max-w-lg mx-auto leading-relaxed font-light"
            style={{ color: "var(--text-secondary)" }}
          >
            возражений менеджер проваливает без подготовки.
            После 30 тренировок — <strong className="font-pixel text-2xl sm:text-3xl" style={{ color: "var(--text-primary)" }}>3 из 10.</strong>
          </p>
        </motion.section>
        <div className="pixel-divider" />

        {/* ── 3. SCORING — broken rhythm: 3 large + 7 compact ── */}
        <section className="pt-6 pb-20">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <h2
              className="font-display font-black tracking-tight"
              style={{ fontSize: "clamp(2rem, 4vw, 3rem)", color: "var(--text-primary)" }}
            >
              Что мы проверяем в каждом звонке
            </h2>
            <p className="text-lg mt-3 max-w-2xl mb-12" style={{ color: "var(--text-secondary)" }}>
              Не «ощущения тренера», а конкретные данные. 10 параметров — от скрипта до ловушек.
            </p>
          </motion.div>

          {/* Primary 3 — large cards, different layout */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            {SCORING_PRIMARY.map(({ name, desc, icon: Icon, ...rest }, i) => {
              const isNeg = "negative" in rest;
              return (
                <motion.div
                  key={name}
                  initial={{ opacity: 0, y: 24 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className="pixel-shadow p-7 sm:p-8"
                  style={{ background: "var(--bg-panel)", border: "2px solid var(--border-color)" }}
                >
                  <div
                    className="w-12 h-12 flex items-center justify-center mb-5"
                    style={{ background: isNeg ? "var(--danger-muted)" : "var(--success-muted)" }}
                  >
                    <Icon size={24} style={{ color: isNeg ? "var(--danger)" : "var(--success)" }} />
                  </div>
                  <h3 className="font-pixel text-2xl mb-2" style={{ color: "var(--text-primary)" }}>{name}</h3>
                  <p className="text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>{desc}</p>
                </motion.div>
              );
            })}
          </div>

          {/* Secondary 7 — compact text rows, no cards */}
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="p-6 sm:p-8"
            style={{ background: "var(--bg-panel)", border: "2px solid var(--border-color)" }}
          >
            <p className="font-pixel text-lg tracking-widest uppercase mb-6" style={{ color: "var(--text-muted)" }}>
              Ещё 7 параметров
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-5">
              {SCORING_SECONDARY.map(({ name, desc, icon: Icon, ...rest }) => {
                const isNeg = "negative" in rest;
                return (
                  <div key={name} className="flex items-center gap-3 py-3" style={{ borderBottom: "1px solid var(--border-color)" }}>
                    <Icon size={18} className="flex-shrink-0" style={{ color: isNeg ? "var(--danger)" : "var(--text-muted)", opacity: 0.6 }} />
                    <div>
                      <span className="font-medium text-base" style={{ color: "var(--text-primary)" }}>{name}</span>
                      <span className="text-base ml-2" style={{ color: "var(--text-muted)" }}>{desc}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        </section>

        {/* ── 4. PVP ARENA — full-width immersive ────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="py-10"
          style={{ borderTop: "none" }}
        >
          <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-12 items-center">
            <div className="space-y-6">
              <div className="flex items-center gap-3">
                <Swords size={28} style={{ color: "var(--text-primary)" }} />
                <h2 className="font-display font-black tracking-tight" style={{ fontSize: "clamp(2rem, 3.5vw, 2.75rem)", color: "var(--text-primary)" }}>
                  PvP-арена
                </h2>
              </div>
              <p className="text-lg leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                Менеджеры соревнуются друг с другом в реальном времени. Рейтинговая система — от Bronze до Diamond. Каждая победа приближает к следующему рангу.
              </p>

              {/* Features as simple text, not cards */}
              <div className="space-y-4 pt-2">
                <div className="flex items-start gap-3">
                  <Trophy size={18} className="mt-1 flex-shrink-0" style={{ color: "var(--success)" }} />
                  <p className="text-base" style={{ color: "var(--text-secondary)" }}>
                    <strong style={{ color: "var(--text-primary)" }}>Ранговые дуэли</strong> — побеждайте в серии из 3 матчей, чтобы подняться выше.
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <Flame size={18} className="mt-1 flex-shrink-0" style={{ color: "var(--success)" }} />
                  <p className="text-base" style={{ color: "var(--text-secondary)" }}>
                    <strong style={{ color: "var(--text-primary)" }}>Сезонные награды</strong> — лучшие охотники получают уникальные бонусы и XP.
                  </p>
                </div>
              </div>
            </div>

            {/* Rank visualization */}
            <div className="pixel-border p-7 sm:p-8" style={{ background: "var(--bg-panel)" }}>
              <h3 className="font-pixel text-xl mb-1" style={{ color: "var(--text-muted)" }}>
                5 рангов — от Bronze до Diamond
              </h3>
              <p className="text-xs mb-5" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
                Целевое распределение
              </p>
              <div className="space-y-4">
                {PVP_RANKS.map(({ name, divisions, color, pct, icon }) => (
                  <div key={name} className="flex items-center gap-4">
                    <Image
                      src={icon}
                      alt={name}
                      width={24}
                      height={24}
                      className="flex-shrink-0 render-pixel"
                    />
                    <span className="font-pixel text-xl w-24" style={{ color }}>{name}</span>
                    <div className="flex gap-0.5 flex-1">
                      {Array.from({ length: divisions }).map((_, i) => (
                        <div key={i} className="h-3 flex-1" style={{ background: color, opacity: 0.15 + (i * 0.3) }} />
                      ))}
                    </div>
                    <span className="font-pixel text-lg w-10 text-right" style={{ color: "var(--text-muted)" }}>{pct}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </motion.section>

        {/* ── 5. Activity ticker ──────────────────────────────── */}
        <div
          className="overflow-hidden py-5"
          style={{
            borderTop: "1px solid var(--border-color)",
            borderBottom: "1px solid var(--border-color)",
            WebkitMaskImage: "linear-gradient(to right, transparent 0%, black 8%, black 92%, transparent 100%)",
            maskImage: "linear-gradient(to right, transparent 0%, black 8%, black 92%, transparent 100%)",
          }}
        >
          <motion.div
            className="flex gap-8 whitespace-nowrap"
            animate={{ x: [0, -1200] }}
            transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
          >
            {[
              "Иван М. → Silver III (+42 pts)",
              "Команда BankHelp → 87 тренировок в марте",
              "Анна К. → закрыла 3 сделки после тренировки",
              "Отдел продаж FinLead → +34% конверсия за квартал",
              "Дмитрий С. → Gold I (новый ранг!)",
              "Команда DebtPro → 12 менеджеров, 240 тренировок",
              "Иван М. → Silver III (+42 pts)",
              "Команда BankHelp → 87 тренировок в марте",
              "Анна К. → закрыла 3 сделки после тренировки",
              "Отдел продаж FinLead → +34% конверсия за квартал",
            ].map((item, i) => (
              <span key={i} className="font-pixel text-lg" style={{ color: "var(--text-muted)" }}>
                {item}
              </span>
            ))}
          </motion.div>
        </div>

        {/* ── 6. GAMIFICATION — asymmetric: big + small ───────── */}
        <section className="pt-20 pb-10">
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="font-display font-black tracking-tight mb-10"
            style={{ fontSize: "clamp(2rem, 4vw, 3rem)", color: "var(--text-primary)" }}
          >
            Мотивация и управление
          </motion.h2>

          {/* Asymmetric: one big card + two small */}
          <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-6">
            {/* Big card — gamification */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="pixel-border p-8 sm:p-10 lg:row-span-2"
              style={{ background: "var(--bg-panel)" }}
            >
              <Star size={28} style={{ color: "var(--text-muted)" }} />
              <h3 className="font-pixel text-3xl mt-5 mb-3" style={{ color: "var(--text-primary)" }}>
                35+ достижений и 20 уровней
              </h3>
              <p className="text-lg leading-relaxed mb-6" style={{ color: "var(--text-secondary)" }}>
                От «Первый звонок» до «Легендарный охотник». Редкие, эпические, легендарные.
                Каждый уровень открывает новые сценарии и типы клиентов.
              </p>
              {/* Achievement examples with pixel sprites */}
              <div className="flex flex-wrap gap-3">
                {ACHIEVEMENT_BADGES.map(({ label, sprite }) => (
                  <div
                    key={label}
                    className="pixel-border flex items-center gap-2 px-3 py-2"
                    style={{ background: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                  >
                    <Image
                      src={sprite}
                      alt={label}
                      width={20}
                      height={20}
                      className="render-pixel"
                    />
                    <span className="font-pixel text-base">{label}</span>
                  </div>
                ))}
              </div>
            </motion.div>

            {/* Small card — streaks */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="rounded-xl p-6"
              style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
            >
              <Flame size={20} style={{ color: "var(--success)" }} />
              <h3 className="font-pixel text-xl mt-3 mb-1" style={{ color: "var(--text-primary)" }}>Стрики и дейлики</h3>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Ежедневные цели. Серии тренировок = бонусный XP.
              </p>
            </motion.div>

            {/* Small card — progress */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.15 }}
              className="rounded-xl p-6"
              style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
            >
              <TrendingUp size={20} style={{ color: "var(--success)" }} />
              <h3 className="font-pixel text-xl mt-3 mb-1" style={{ color: "var(--text-primary)" }}>Прогресс команды</h3>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Дашборд руководителя. Кто растёт, кто буксует.
              </p>
            </motion.div>
          </div>
        </section>

        {/* ── 7. CRM + Knowledge — simple text, not cards ─────── */}
        <div className="pixel-divider" />
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="grid grid-cols-1 sm:grid-cols-2 gap-12 py-16"
        >
          <div>
            <Users size={22} className="mb-4" style={{ color: "var(--text-muted)" }} />
            <h3 className="font-pixel text-2xl mb-3" style={{ color: "var(--text-primary)" }}>CRM-модуль</h3>
            <p className="text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              Управляйте клиентами прямо в платформе. 12 статусов — от первого контакта до закрытия. Полное соответствие 152-ФЗ и 127-ФЗ.
            </p>
          </div>
          <div>
            <BookOpen size={22} className="mb-4" style={{ color: "var(--text-muted)" }} />
            <h3 className="font-pixel text-2xl mb-3" style={{ color: "var(--text-primary)" }}>База знаний 127-ФЗ</h3>
            <p className="text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              Квиз-система по закону о банкротстве. Блиц-режим, автоматическая проверка юридических знаний вашей команды.
            </p>
          </div>
        </motion.section>

      </div>
    </div>
  );
}
