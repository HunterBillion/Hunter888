"use client";

import { motion } from "framer-motion";
import { BookOpen, FileText, Settings, Database, ChevronRight, ShieldAlert } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import { hasRole } from "@/lib/guards";

const TOOLS = [
  {
    title: "Просмотр сессий",
    description: "Все тренировочные сессии с фильтрами и детализацией",
    icon: FileText,
    href: "/methodologist/sessions",
    color: "#5B9FE5",
  },
  {
    title: "Управление сценариями",
    description: "Создание и редактирование сценариев тренировок",
    icon: BookOpen,
    href: "/methodologist/scenarios",
    color: "#818CF8",
  },
  {
    title: "Контент Арены",
    description: "CRUD для базы знаний ФЗ-127 (чанки, вопросы)",
    icon: Database,
    href: "/methodologist/arena-content",
    color: "#F59E0B",
  },
  {
    title: "Настройки скоринга",
    description: "Веса L1-L10 и пороговые значения",
    icon: Settings,
    href: "/methodologist/scoring",
    color: "#22C55E",
  },
];

export default function MethodologistPage() {
  const { user, loading: authLoading } = useAuth();
  const accessDenied = !authLoading && user != null && !hasRole(user, ["admin", "rop", "methodologist"]);

  if (accessDenied) {
    return (
      <AuthLayout>
        <div className="flex min-h-screen items-center justify-center">
          <div className="text-center">
            <ShieldAlert size={48} style={{ color: "var(--neon-red)", margin: "0 auto 16px" }} />
            <h2 className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>Доступ запрещён</h2>
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>Эта страница доступна только методологам, РОП и администраторам.</p>
          </div>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="app-page max-w-3xl">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <h1 className="font-display text-2xl font-bold tracking-[0.15em]" style={{ color: "var(--text-primary)" }}>
              МЕТОДОЛОГ
            </h1>
            <p className="mt-1 font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)" }}>
              Инструменты управления контентом и оценкой
            </p>
          </motion.div>

          <div className="mt-8 grid gap-4">
            {TOOLS.map((tool, i) => (
              <Link key={tool.href} href={tool.href}>
                <motion.div
                  initial={{ opacity: 0, x: -16 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.08 }}
                  className="flex items-center gap-4 rounded-xl p-5 cursor-pointer transition-all hover:scale-[1.01]"
                  style={{
                    background: "var(--glass-bg)",
                    border: "1px solid var(--glass-border)",
                    backdropFilter: "blur(20px)",
                  }}
                >
                  <div
                    className="flex h-12 w-12 items-center justify-center rounded-xl"
                    style={{ background: `${tool.color}15`, border: `1px solid ${tool.color}30` }}
                  >
                    <tool.icon size={22} style={{ color: tool.color }} />
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      {tool.title}
                    </div>
                    <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {tool.description}
                    </div>
                  </div>
                  <ChevronRight size={16} style={{ color: "var(--text-muted)" }} />
                </motion.div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}
