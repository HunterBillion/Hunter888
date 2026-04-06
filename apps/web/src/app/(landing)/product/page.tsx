"use client";

import { motion } from "framer-motion";
import {
  Brain,
  Mic,
  Target,
  Shield,
  Swords,
  Trophy,
  BarChart3,
  Users,
  BookOpen,
  Scale,
  Flame,
  Star,
  ChevronRight,
  Zap,
  AlertTriangle,
  MessageSquare,
  Timer,
  UserCheck,
  Layers,
  TrendingUp,
} from "lucide-react";

/* ── Scoring Layers ───────────────────────────────────────────────── */
const SCORING_MAIN = [
  { id: "L1", name: "Скрипт", points: "0–30", desc: "Следование этапам диалога, прохождение чекпоинтов", icon: Target, color: "var(--accent)" },
  { id: "L2", name: "Возражения", points: "0–25", desc: "Обработка возражений по цене, доверию, срочности, конкурентам", icon: Shield, color: "var(--neon-green)" },
  { id: "L3", name: "Коммуникация", points: "0–20", desc: "Эмпатия, вежливость, скорость реакции", icon: MessageSquare, color: "var(--accent)" },
  { id: "L4", name: "Антипаттерны", points: "−5", desc: "Детекция ложных обещаний, гарантий, манипуляций", icon: AlertTriangle, color: "var(--neon-red)" },
  { id: "L5", name: "Результат", points: "0–10", desc: "Достижение цели: консультация, встреча, сделка", icon: Trophy, color: "var(--neon-green)" },
] as const;

const SCORING_EXTRA = [
  { id: "L6", name: "Человеческий фактор", desc: "±15 баллов за работу с эмоциями клиента" },
  { id: "L7", name: "Нарратив", desc: "10 баллов за логику развития разговора" },
  { id: "L8", name: "Юр. точность", desc: "±5 модификатор за соответствие 127-ФЗ" },
  { id: "L9", name: "Soft Skills", desc: "Talk/listen ratio, паузы, обращение по имени" },
  { id: "L10", name: "Детекция ловушек", desc: "Динамический бонус/штраф за 15 типов ловушек" },
] as const;

/* ── PvP Ranks ────────────────────────────────────────────────────── */
const PVP_RANKS = [
  { name: "Bronze", divisions: 3, color: "#CD7F32" },
  { name: "Silver", divisions: 3, color: "#C0C0C0" },
  { name: "Gold", divisions: 3, color: "#FFD700" },
  { name: "Platinum", divisions: 3, color: "#E5E4E2" },
  { name: "Diamond", divisions: 3, color: "#B9F2FF" },
] as const;

/* ── Features ─────────────────────────────────────────────────────── */
const FEATURES = [
  { icon: Flame, title: "Стрики и дейлики", desc: "Ежедневные цели с XP-наградами. Стрики за серии тренировок." },
  { icon: Star, title: "35+ ачивок", desc: "Rare, Epic, Legendary. Разблокируйте за особые достижения." },
  { icon: TrendingUp, title: "20 уровней прогресса", desc: "Система XP от Новичка до Эксперта с разблокировкой контента." },
] as const;

/* ═══════════════════════════ PAGE ═════════════════════════════════ */
export default function ProductPage() {
  return (
    <div
      className="relative min-h-screen"
      style={{ background: "var(--bg-primary)", paddingTop: "96px" }}
    >
      {/* Geometric grid bg */}
      <div
        className="fixed inset-0 opacity-[0.02] pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(to right, var(--text-muted) 1px, transparent 1px),
                            linear-gradient(to bottom, var(--text-muted) 1px, transparent 1px)`,
          backgroundSize: "40px 40px",
        }}
      />

      <div className="relative z-10 max-w-7xl mx-auto px-5 sm:px-8 md:px-10 py-12 sm:py-20 space-y-24">

        {/* ── HERO: AI Training ───────────────────────────────── */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7 }}
            className="lg:col-span-7 space-y-6"
          >
            <div
              className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono tracking-widest"
              style={{ background: "var(--accent-muted)", border: "1px solid var(--border-color)", color: "var(--neon-green)" }}
            >
              <motion.span
                className="w-2 h-2 rounded-full"
                style={{ background: "var(--neon-green)" }}
                animate={{ opacity: [1, 0.3, 1] }}
                transition={{ duration: 1.8, repeat: Infinity }}
              />
              NEURAL_TRAINING: ACTIVE
            </div>

            <h1
              className="font-display font-black tracking-tighter leading-none uppercase"
              style={{ fontSize: "clamp(2.5rem, 5.5vw, 4.5rem)", color: "var(--text-primary)" }}
            >
              Тренировки<br />
              <span style={{ color: "var(--accent)" }}>нового поколения</span>
            </h1>

            <p className="text-base sm:text-lg max-w-2xl leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              Диалоговые симуляции с ИИ-клиентами, которые возражают, давят, торгуются и манипулируют.
              100 архетипов поведения. 60 сценариев от холодного звонка до кризиса.
              10-слойная система скоринга разбирает каждую фразу.
            </p>

            <div className="flex flex-wrap gap-4 pt-2">
              <div className="p-5 rounded-lg flex-1 min-w-[140px]" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
                <div className="text-2xl sm:text-3xl font-black mb-1" style={{ color: "var(--accent)" }}>6000+</div>
                <div className="text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>КОМБИНАЦИЙ</div>
              </div>
              <div className="p-5 rounded-lg flex-1 min-w-[140px]" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
                <div className="text-2xl sm:text-3xl font-black mb-1" style={{ color: "var(--neon-green)" }}>10</div>
                <div className="text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>СЛОЁВ СКОРИНГА</div>
              </div>
              <div className="p-5 rounded-lg flex-1 min-w-[140px]" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
                <div className="flex items-center gap-2 text-2xl sm:text-3xl font-black mb-1" style={{ color: "var(--accent)" }}>
                  <Mic size={22} />
                  <span>Voice</span>
                </div>
                <div className="text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>ГОЛОСОВОЙ РЕЖИМ</div>
              </div>
            </div>
          </motion.div>

          {/* Image slot */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="lg:col-span-5 relative group"
          >
            <div
              className="absolute -inset-0.5 opacity-20 blur group-hover:opacity-30 transition duration-500 rounded-xl"
              style={{ background: "linear-gradient(to right, var(--accent), var(--neon-green))" }}
            />
            <div
              className="relative rounded-xl overflow-hidden aspect-square"
              style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
            >
              {/* TODO: Заменить на реальное изображение — слот для пользовательского ассета */}
              <div className="w-full h-full flex flex-col items-center justify-center gap-4" style={{ background: "linear-gradient(135deg, var(--bg-tertiary) 0%, var(--accent-muted) 40%, var(--bg-tertiary) 100%)" }}>
                <Brain size={64} style={{ color: "var(--accent)", opacity: 0.3 }} />
                <span className="text-xs font-mono" style={{ color: "var(--text-muted)", opacity: 0.5 }}>TRAINING_VISUAL_SLOT</span>
              </div>
              <div className="absolute inset-0" style={{ background: "linear-gradient(to top, var(--bg-primary) 0%, transparent 60%)", opacity: 0.6 }} />
              <div className="absolute bottom-6 left-6 right-6 font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
                &gt; SCENARIO_LOADED: OUTBOUND_COLD_A3<br />
                &gt; ARCHETYPE: NEGOTIATOR // DIFFICULTY: 7
              </div>
            </div>
          </motion.div>
        </section>

        {/* ── SCORING SYSTEM (10 layers) ──────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="space-y-8"
        >
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-end gap-4">
            <div>
              <h2 className="text-2xl sm:text-3xl font-black tracking-tight uppercase" style={{ color: "var(--text-primary)" }}>
                10-СЛОЙНЫЙ СКОРИНГ
              </h2>
              <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                Каждая тренировка анализируется по 10 независимым слоям. Не ощущения — данные.
              </p>
            </div>
            <div className="hidden md:block h-[1px] flex-grow mx-8 mb-3" style={{ background: "var(--border-color)" }} />
            <div className="flex items-center gap-2">
              <Layers size={16} style={{ color: "var(--accent)" }} />
              <span className="text-xs font-mono tracking-wider uppercase" style={{ color: "var(--text-muted)" }}>PRECISION_SCORING</span>
            </div>
          </div>

          {/* Main 5 layers — bento grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {SCORING_MAIN.map(({ id, name, points, desc, icon: Icon, color }, i) => (
              <motion.div
                key={id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.08 }}
                className="rounded-xl p-5 space-y-3 group"
                style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
              >
                <div className="flex justify-between items-center">
                  <Icon size={20} style={{ color }} />
                  <span className="text-[10px] font-mono font-bold tracking-wider" style={{ color }}>{id}</span>
                </div>
                <h4 className="font-bold text-sm" style={{ color: "var(--text-primary)" }}>{name}</h4>
                <div className="text-xs font-mono font-bold" style={{ color }}>{points} pts</div>
                <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>{desc}</p>
              </motion.div>
            ))}
          </div>

          {/* Extra 5 layers — compact list */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {SCORING_EXTRA.map(({ id, name, desc }) => (
              <div
                key={id}
                className="rounded-lg px-4 py-3 flex items-start gap-3"
                style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}
              >
                <span className="text-[10px] font-mono font-bold mt-0.5 flex-shrink-0" style={{ color: "var(--accent)" }}>{id}</span>
                <div>
                  <div className="text-xs font-bold" style={{ color: "var(--text-primary)" }}>{name}</div>
                  <div className="text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>{desc}</div>
                </div>
              </div>
            ))}
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
              <h2 className="font-display font-black tracking-tighter uppercase" style={{ fontSize: "clamp(2rem, 3.5vw, 2.75rem)", color: "var(--text-primary)" }}>
                PVP АРЕНА
              </h2>
            </div>
            <p className="leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              Менеджеры соревнуются в реальном времени. Система рейтинга Glicko-2 — как в шахматах.
              24 ранга от Bronze до Diamond. Сезонные турниры с наградами.
            </p>
            <ul className="space-y-4">
              <li className="flex items-start gap-3">
                <Trophy size={18} className="mt-1 flex-shrink-0" style={{ color: "var(--neon-green)" }} />
                <div>
                  <span className="block font-bold" style={{ color: "var(--text-primary)" }}>Ранговые дуэли</span>
                  <span className="text-sm" style={{ color: "var(--text-secondary)" }}>BO3 промо-серии для повышения дивизиона. Anti-cheat и rating freeze.</span>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <Flame size={18} className="mt-1 flex-shrink-0" style={{ color: "var(--neon-green)" }} />
                <div>
                  <span className="block font-bold" style={{ color: "var(--text-primary)" }}>Сезонные награды</span>
                  <span className="text-sm" style={{ color: "var(--text-secondary)" }}>По итогам сезона лучшие охотники получают уникальные награды и бонусы XP.</span>
                </div>
              </li>
            </ul>
          </div>

          {/* Rank visualization */}
          <div
            className="rounded-xl p-8 flex flex-col justify-center relative overflow-hidden"
            style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
          >
            <h3 className="font-mono text-xs tracking-widest uppercase mb-6" style={{ color: "var(--text-muted)" }}>
              РАНГОВАЯ СИСТЕМА — 24 РАНГА
            </h3>
            <div className="space-y-3">
              {PVP_RANKS.map(({ name, divisions, color }) => (
                <div key={name} className="flex items-center gap-4">
                  <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
                  <span className="font-bold text-sm w-20" style={{ color }}>{name}</span>
                  <div className="flex gap-1 flex-1">
                    {Array.from({ length: divisions }).map((_, i) => (
                      <div key={i} className="h-2 flex-1 rounded-full" style={{ background: color, opacity: 0.2 + (i * 0.3) }} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-6 text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
              RATING_SYSTEM: GLICKO-2 // PROMOTION: BO3_SERIES
            </div>
          </div>
        </motion.section>

        {/* ── GAMIFICATION + CRM ──────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="space-y-8"
        >
          <h2 className="text-2xl sm:text-3xl font-black tracking-tight uppercase" style={{ color: "var(--text-primary)" }}>
            ГЕЙМИФИКАЦИЯ И CRM
          </h2>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Gamification features */}
            <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-3 gap-4">
              {FEATURES.map(({ icon: Icon, title, desc }, i) => (
                <motion.div
                  key={title}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className="rounded-xl p-5 space-y-3"
                  style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
                >
                  <Icon size={22} style={{ color: "var(--accent)" }} />
                  <h4 className="font-bold text-sm" style={{ color: "var(--text-primary)" }}>{title}</h4>
                  <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>{desc}</p>
                </motion.div>
              ))}
            </div>

            {/* CRM module */}
            <div
              className="rounded-xl p-6 space-y-4"
              style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
            >
              <div className="flex items-center gap-3">
                <Users size={22} style={{ color: "var(--accent)" }} />
                <h4 className="font-bold" style={{ color: "var(--text-primary)" }}>CRM-модуль</h4>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                Управление реальными клиентами прямо в платформе. 12-статусный пайплайн от первого контакта до закрытия.
              </p>
              <div className="space-y-2">
                {["152-ФЗ Compliance", "Аудит-трейл", "Soft-delete", "127-ФЗ Тестирование"].map((item) => (
                  <div key={item} className="flex items-center gap-2">
                    <Scale size={12} style={{ color: "var(--neon-green)" }} />
                    <span className="text-xs" style={{ color: "var(--text-secondary)" }}>{item}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Knowledge module */}
          <div
            className="rounded-xl p-6 flex flex-col sm:flex-row items-start sm:items-center gap-6"
            style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}
          >
            <div className="flex-shrink-0 w-16 h-16 rounded-lg flex items-center justify-center" style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}>
              <BookOpen size={28} style={{ color: "var(--accent)" }} />
            </div>
            <div className="flex-1">
              <h4 className="font-bold text-base" style={{ color: "var(--text-primary)" }}>База знаний 127-ФЗ</h4>
              <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                Квиз-система по закону о банкротстве. Блиц-режим, арена контента для методологов, автоматическая проверка юридических знаний.
              </p>
            </div>
            <ChevronRight size={20} style={{ color: "var(--text-muted)" }} />
          </div>
        </motion.section>
      </div>
    </div>
  );
}
