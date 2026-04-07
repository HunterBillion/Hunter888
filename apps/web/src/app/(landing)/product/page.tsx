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
  ChevronRight,
} from "lucide-react";

/* ── All 10 scoring parameters — human language ──────────────────── */
const SCORING = [
  { name: "Скрипт", desc: "Следуете этапам разговора? Не пропускаете ключевые моменты?", icon: Target },
  { name: "Возражения", desc: "Клиент говорит «дорого» или «не сейчас» — как реагируете?", icon: Shield },
  { name: "Коммуникация", desc: "Эмпатия, вежливость, скорость реакции — всё считается.", icon: MessageSquare },
  { name: "Ошибки", desc: "Ловим ложные обещания, давление и манипуляции. За них — штраф.", icon: AlertTriangle, negative: true },
  { name: "Результат", desc: "Назначили встречу? Получили согласие? Закрыли сделку?", icon: Trophy },
  { name: "Эмоции", desc: "Как вы работаете с тревогой, агрессией и отчаянием клиента.", icon: Brain },
  { name: "Логика диалога", desc: "Разговор развивается последовательно или скачет хаотично?", icon: Target },
  { name: "Юр. точность", desc: "Соответствие 127-ФЗ — правильно ли вы информируете клиента.", icon: Scale },
  { name: "Баланс речи", desc: "Сколько говорите vs слушаете. Паузы. Обращение по имени.", icon: Mic },
  { name: "Ловушки", desc: "15 типов провокаций от ИИ-клиента. Попались — штраф.", icon: AlertTriangle, negative: true },
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

      <div className="relative z-10 max-w-6xl mx-auto px-5 sm:px-8 md:px-10 py-12 sm:py-20 space-y-28">

        {/* ── HERO ────────────────────────────────────────────── */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
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
              <span style={{ color: "var(--accent)" }}>X Hunter</span>
            </h1>

            <p className="text-lg sm:text-xl max-w-xl leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              <strong style={{ color: "var(--text-primary)" }}>Шаг 1:</strong> Менеджер выбирает ситуацию — холодный звонок, жёсткие переговоры, кризис.{" "}
              <strong style={{ color: "var(--text-primary)" }}>Шаг 2:</strong> Разговаривает с ИИ, который ведёт себя как настоящий клиент.{" "}
              <strong style={{ color: "var(--text-primary)" }}>Шаг 3:</strong> Получает детальный разбор — что сработало, а где потерял клиента.
            </p>

            <div className="flex flex-wrap gap-5 pt-3">
              <div className="flex items-center gap-3 text-base" style={{ color: "var(--text-secondary)" }}>
                <Brain size={20} style={{ color: "var(--accent)" }} />
                <span><strong style={{ color: "var(--text-primary)" }}>60</strong> реальных сценариев</span>
              </div>
              <div className="flex items-center gap-3 text-base" style={{ color: "var(--text-secondary)" }}>
                <Users size={20} style={{ color: "var(--accent)" }} />
                <span><strong style={{ color: "var(--text-primary)" }}>100</strong> типов клиентов</span>
              </div>
              <div className="flex items-center gap-3 text-base" style={{ color: "var(--text-secondary)" }}>
                <Mic size={20} style={{ color: "var(--accent)" }} />
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
              {/* Neural Network Matrix image — place file at public/landing/neural-matrix.jpg */}
              <img
                src="/landing/neural-matrix.jpg"
                alt="Neural Network Matrix — визуализация архитектуры ИИ-скоринга X Hunter"
                className="w-full h-full object-cover"
                onError={(e) => {
                  // Fallback gradient if image not found
                  (e.target as HTMLImageElement).style.display = "none";
                  (e.target as HTMLImageElement).parentElement!.style.background = "linear-gradient(135deg, var(--bg-tertiary) 0%, var(--accent-muted) 40%, var(--bg-tertiary) 100%)";
                }}
              />
              <div className="absolute inset-0 pointer-events-none" style={{ background: "linear-gradient(to top, var(--bg-primary) 0%, transparent 40%)" }} />
            </div>
          </motion.div>
        </section>

        {/* ── SCORING — what we check ─────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="space-y-10"
        >
          <div>
            <h2
              className="font-display font-black tracking-tight"
              style={{ fontSize: "clamp(2rem, 4vw, 3rem)", color: "var(--text-primary)" }}
            >
              Что мы проверяем в каждом звонке
            </h2>
            <p className="text-lg mt-3 max-w-2xl" style={{ color: "var(--text-secondary)" }}>
              Не «ощущения тренера», а конкретные данные. 10 параметров — от скрипта до ловушек.
            </p>
          </div>

          {/* All 10 scoring parameters — clean 2-column grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {SCORING.map(({ name, desc, icon: Icon, ...rest }, i) => {
              const isNeg = "negative" in rest;
              return (
                <motion.div
                  key={name}
                  initial={{ opacity: 0, y: 16 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.05 }}
                  className="rounded-xl p-5 sm:p-6 flex items-start gap-4"
                  style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
                >
                  <div
                    className="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center mt-0.5"
                    style={{ background: isNeg ? "rgba(255,42,109,0.08)" : "var(--accent-muted)" }}
                  >
                    <Icon size={20} style={{ color: isNeg ? "var(--neon-red)" : "var(--accent)" }} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-display font-bold text-base" style={{ color: "var(--text-primary)" }}>{name}</h3>
                      <span className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>{i + 1}/10</span>
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>{desc}</p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </motion.section>

        {/* ── PVP ARENA ───────────────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="grid grid-cols-1 lg:grid-cols-2 gap-10 py-12"
          style={{ borderTop: "1px solid var(--border-color)", borderBottom: "1px solid var(--border-color)" }}
        >
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <Swords size={28} style={{ color: "var(--accent)" }} />
              <h2 className="font-display font-black tracking-tight" style={{ fontSize: "clamp(2rem, 3.5vw, 2.75rem)", color: "var(--text-primary)" }}>
                PvP-арена
              </h2>
            </div>
            <p className="text-lg leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              Менеджеры соревнуются друг с другом в реальном времени. Рейтинговая система как в шахматах — 24 ранга от Bronze до Diamond.
            </p>
            <ul className="space-y-5">
              <li className="flex items-start gap-3">
                <Trophy size={20} className="mt-1 flex-shrink-0" style={{ color: "var(--neon-green)" }} />
                <div>
                  <span className="block text-base font-bold" style={{ color: "var(--text-primary)" }}>Ранговые дуэли</span>
                  <span className="text-base" style={{ color: "var(--text-secondary)" }}>Побеждайте в серии из 3 матчей, чтобы подняться выше.</span>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <Flame size={20} className="mt-1 flex-shrink-0" style={{ color: "var(--neon-green)" }} />
                <div>
                  <span className="block text-base font-bold" style={{ color: "var(--text-primary)" }}>Сезонные награды</span>
                  <span className="text-base" style={{ color: "var(--text-secondary)" }}>Лучшие охотники сезона получают уникальные бонусы и XP.</span>
                </div>
              </li>
            </ul>
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
        </motion.section>

        {/* ── Activity ticker — social proof ────────────────── */}
        <div
          className="overflow-hidden py-6 relative"
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

        {/* ── GAMIFICATION + CRM ──────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="space-y-8"
        >
          <h2 className="font-display font-black tracking-tight" style={{ fontSize: "clamp(2rem, 4vw, 3rem)", color: "var(--text-primary)" }}>
            Мотивация и управление
          </h2>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {[
              { icon: Flame, title: "Стрики и дейлики", desc: "Ежедневные цели с наградами. Серии тренировок приносят бонусный XP." },
              { icon: Star, title: "35+ достижений", desc: "От «Первый звонок» до «Легендарный охотник». Редкие, эпические, легендарные." },
              { icon: TrendingUp, title: "20 уровней", desc: "Система прогресса от новичка до эксперта. Каждый уровень открывает новый контент." },
            ].map(({ icon: Icon, title, desc }, i) => (
              <motion.div
                key={title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="rounded-xl p-6 sm:p-7"
                style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
              >
                <Icon size={24} style={{ color: "var(--accent)" }} />
                <h3 className="font-display font-bold text-lg mt-4 mb-2" style={{ color: "var(--text-primary)" }}>{title}</h3>
                <p className="text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>{desc}</p>
              </motion.div>
            ))}
          </div>

          {/* CRM + Knowledge bottom row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div className="rounded-xl p-6 sm:p-7" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
              <div className="flex items-center gap-3 mb-4">
                <Users size={24} style={{ color: "var(--accent)" }} />
                <h3 className="font-display font-bold text-lg" style={{ color: "var(--text-primary)" }}>CRM-модуль</h3>
              </div>
              <p className="text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                Управляйте клиентами прямо в платформе. 12 статусов — от первого контакта до закрытия. Полное соответствие 152-ФЗ и 127-ФЗ.
              </p>
            </div>
            <div className="rounded-xl p-6 sm:p-7" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
              <div className="flex items-center gap-3 mb-4">
                <BookOpen size={24} style={{ color: "var(--accent)" }} />
                <h3 className="font-display font-bold text-lg" style={{ color: "var(--text-primary)" }}>База знаний 127-ФЗ</h3>
              </div>
              <p className="text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                Квиз-система по закону о банкротстве. Блиц-режим, автоматическая проверка юридических знаний вашей команды.
              </p>
            </div>
          </div>
        </motion.section>
      </div>
    </div>
  );
}
