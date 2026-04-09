"use client";

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
  { name: "Bronze", divisions: 3, color: "#CD7F32", pct: "47%" },
  { name: "Silver", divisions: 3, color: "#C0C0C0", pct: "28%" },
  { name: "Gold", divisions: 3, color: "#FFD700", pct: "15%" },
  { name: "Platinum", divisions: 3, color: "#E5E4E2", pct: "8%" },
  { name: "Diamond", divisions: 3, color: "#B9F2FF", pct: "2%" },
] as const;

/* ═══════════════════════════ PAGE ═════════════════════════════════ */
export default function ProductPage() {
  return (
    <div
      className="relative min-h-screen"
      style={{ background: "var(--bg-primary)", paddingTop: "96px" }}
    >
      <div className="absolute inset-0 opacity-[0.02] pointer-events-none" style={{ backgroundImage: `linear-gradient(to right, var(--text-muted) 1px, transparent 1px), linear-gradient(to bottom, var(--text-muted) 1px, transparent 1px)`, backgroundSize: "40px 40px" }} />

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

            <p className="text-lg sm:text-xl max-w-xl leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              <strong style={{ color: "var(--text-primary)" }}>Шаг 1:</strong> Менеджер выбирает ситуацию — холодный звонок, жёсткие переговоры, кризис.{" "}
              <strong style={{ color: "var(--text-primary)" }}>Шаг 2:</strong> Разговаривает с ИИ, который ведёт себя как настоящий клиент.{" "}
              <strong style={{ color: "var(--text-primary)" }}>Шаг 3:</strong> Получает детальный разбор — что сработало, а где потерял клиента.
            </p>

            <div className="flex flex-wrap gap-5 pt-3">
              <div className="flex items-center gap-3 text-base" style={{ color: "var(--text-secondary)" }}>
                <Brain size={20} style={{ color: "var(--text-muted)" }} />
                <span><strong style={{ color: "var(--text-primary)" }}>60</strong> реальных сценариев</span>
              </div>
              <div className="flex items-center gap-3 text-base" style={{ color: "var(--text-secondary)" }}>
                <Users size={20} style={{ color: "var(--text-muted)" }} />
                <span><strong style={{ color: "var(--text-primary)" }}>100</strong> типов клиентов</span>
              </div>
              <div className="flex items-center gap-3 text-base" style={{ color: "var(--text-secondary)" }}>
                <Mic size={20} style={{ color: "var(--text-muted)" }} />
                <span>Голосовой режим</span>
              </div>
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
        <motion.section
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-center py-16 sm:py-24"
        >
          <p className="text-sm font-medium tracking-widest uppercase mb-4" style={{ color: "var(--text-muted)" }}>
            По данным внутреннего тестирования
          </p>
          <div className="font-display font-extralight leading-none" style={{ fontSize: "clamp(4rem, 12vw, 9rem)", color: "var(--text-primary)" }}>
            7 <span className="text-[0.5em]" style={{ color: "var(--text-muted)" }}>из</span> 10
          </div>
          <p
            className="mt-6 text-xl sm:text-2xl max-w-lg mx-auto leading-relaxed font-light"
            style={{ color: "var(--text-secondary)" }}
          >
            возражений менеджер проваливает без подготовки.
            После 30 тренировок — <strong style={{ color: "var(--text-primary)" }}>3 из 10.</strong>
          </p>
        </motion.section>

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
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-8">
            {SCORING_PRIMARY.map(({ name, desc, icon: Icon, ...rest }, i) => {
              const isNeg = "negative" in rest;
              return (
                <motion.div
                  key={name}
                  initial={{ opacity: 0, y: 24 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className="rounded-xl p-7 sm:p-8"
                  style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
                >
                  <div
                    className="w-12 h-12 rounded-lg flex items-center justify-center mb-5"
                    style={{ background: isNeg ? "rgba(255,42,109,0.10)" : "rgba(0,255,148,0.08)" }}
                  >
                    <Icon size={24} style={{ color: isNeg ? "var(--danger)" : "var(--success)" }} />
                  </div>
                  <h3 className="font-display font-bold text-xl mb-2" style={{ color: "var(--text-primary)" }}>{name}</h3>
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
            className="rounded-xl p-6 sm:p-8"
            style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
          >
            <p className="text-sm font-medium tracking-widest uppercase mb-6" style={{ color: "var(--text-muted)" }}>
              Ещё 7 параметров
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-5">
              {SCORING_SECONDARY.map(({ name, desc, icon: Icon, ...rest }) => {
                const isNeg = "negative" in rest;
                return (
                  <div key={name} className="flex items-start gap-3 py-3" style={{ borderBottom: "1px solid var(--border-color)" }}>
                    <Icon size={18} className="mt-0.5 flex-shrink-0" style={{ color: isNeg ? "var(--danger)" : "var(--text-muted)", opacity: 0.6 }} />
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
          style={{ borderTop: "1px solid var(--border-color)" }}
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
                Менеджеры соревнуются друг с другом в реальном времени. Рейтинговая система как в шахматах — 24 ранга от Bronze до Diamond.
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
            <div className="rounded-xl p-7 sm:p-8" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
              <h3 className="text-base font-bold mb-1" style={{ color: "var(--text-muted)" }}>
                24 ранга — от новичка до мастера
              </h3>
              <p className="text-xs mb-5" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
                Целевое распределение
              </p>
              <div className="space-y-4">
                {PVP_RANKS.map(({ name, divisions, color, pct }) => (
                  <div key={name} className="flex items-center gap-4">
                    <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: color }} />
                    <span className="font-bold text-base w-24" style={{ color }}>{name}</span>
                    <div className="flex gap-1 flex-1">
                      {Array.from({ length: divisions }).map((_, i) => (
                        <div key={i} className="h-2.5 flex-1 rounded-full" style={{ background: color, opacity: 0.15 + (i * 0.3) }} />
                      ))}
                    </div>
                    <span className="text-xs font-medium w-10 text-right" style={{ color: "var(--text-muted)" }}>{pct}</span>
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
            maskImage: "linear-gradient(to right, transparent 0%, black 8%, black 92%, transparent 100%)",
            WebkitMaskImage: "linear-gradient(to right, transparent 0%, black 8%, black 92%, transparent 100%)",
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
              <span key={i} className="text-sm" style={{ color: "var(--text-muted)" }}>
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
          <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-5">
            {/* Big card — gamification */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="rounded-xl p-8 sm:p-10 lg:row-span-2"
              style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
            >
              <Star size={28} style={{ color: "var(--text-muted)" }} />
              <h3 className="font-display font-bold text-2xl mt-5 mb-3" style={{ color: "var(--text-primary)" }}>
                35+ достижений и 20 уровней
              </h3>
              <p className="text-lg leading-relaxed mb-6" style={{ color: "var(--text-secondary)" }}>
                От «Первый звонок» до «Легендарный охотник». Редкие, эпические, легендарные.
                Каждый уровень открывает новые сценарии и типы клиентов.
              </p>
              {/* Achievement examples as inline badges */}
              <div className="flex flex-wrap gap-2">
                {["Первый звонок", "5 побед подряд", "Gold I", "Мастер возражений", "100 тренировок"].map((badge) => (
                  <span
                    key={badge}
                    className="text-xs font-medium px-3 py-1.5 rounded-full"
                    style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)", color: "var(--text-muted)" }}
                  >
                    {badge}
                  </span>
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
              <h3 className="font-display font-bold text-base mt-3 mb-1" style={{ color: "var(--text-primary)" }}>Стрики и дейлики</h3>
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
              <h3 className="font-display font-bold text-base mt-3 mb-1" style={{ color: "var(--text-primary)" }}>Прогресс команды</h3>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Дашборд руководителя. Кто растёт, кто буксует.
              </p>
            </motion.div>
          </div>
        </section>

        {/* ── 7. CRM + Knowledge — simple text, not cards ─────── */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="grid grid-cols-1 sm:grid-cols-2 gap-8 py-16"
          style={{ borderTop: "1px solid var(--border-color)" }}
        >
          <div>
            <Users size={22} className="mb-4" style={{ color: "var(--text-muted)" }} />
            <h3 className="font-display font-bold text-xl mb-3" style={{ color: "var(--text-primary)" }}>CRM-модуль</h3>
            <p className="text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              Управляйте клиентами прямо в платформе. 12 статусов — от первого контакта до закрытия. Полное соответствие 152-ФЗ и 127-ФЗ.
            </p>
          </div>
          <div>
            <BookOpen size={22} className="mb-4" style={{ color: "var(--text-muted)" }} />
            <h3 className="font-display font-bold text-xl mb-3" style={{ color: "var(--text-primary)" }}>База знаний 127-ФЗ</h3>
            <p className="text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              Квиз-система по закону о банкротстве. Блиц-режим, автоматическая проверка юридических знаний вашей команды.
            </p>
          </div>
        </motion.section>

      </div>
    </div>
  );
}
