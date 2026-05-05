"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  BookOpen,
  Brain,
  Target,
  TrendingUp,
  ChevronLeft,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Lightbulb,
} from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import { useAuthStore } from "@/stores/useAuthStore";
import { api } from "@/lib/api";
import AuthLayout from "@/components/layout/AuthLayout";

interface WikiPage {
  page_path: string;
  page_type: string;
  version: number;
  content?: string;
  tags: string[];
  created_at: string | null;
  updated_at: string | null;
}

interface Pattern {
  id: string;
  pattern_code: string;
  category: string;
  description: string;
  sessions_in_pattern: number;
  confirmed_at: string | null;
}

interface Technique {
  id: string;
  technique_code: string;
  technique_name: string;
  success_count: number;
  attempt_count: number;
  success_rate: number;
}

type Tab = "overview" | "patterns" | "techniques";

const CATEGORY_LABELS: Record<string, { label: string; color: string; icon: typeof Target }> = {
  weakness: { label: "Слабость", color: "var(--danger)", icon: AlertTriangle },
  strength: { label: "Сила", color: "var(--success)", icon: CheckCircle2 },
  quirk: { label: "Особенность", color: "var(--warning)", icon: Lightbulb },
  misconception: { label: "Заблуждение", color: "var(--info)", icon: Brain },
};

export default function MyWikiPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const userId = user?.id;
  const role = user?.role;
  const [tab, setTab] = useState<Tab>("overview");
  const [pages, setPages] = useState<WikiPage[]>([]);
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [techniques, setTechniques] = useState<Technique[]>([]);
  const [selectedPage, setSelectedPage] = useState<WikiPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Redirect admin/rop to the canonical Wiki sub-tab inside Контент.
  // (`?tab=wiki` doesn't exist as a top-level tab — wiki is one of the
  // sub-tabs under content. Without &sub=wiki the user lands on the
  // first sub-tab «РОПы», which is wrong.)
  useEffect(() => {
    if (role === "admin" || role === "rop") {
      router.replace("/dashboard?tab=content&sub=wiki");
      return;
    }
    if (!userId) return;

    const fetchAll = async () => {
      setLoading(true);
      setError(null);
      try {
        const [pagesRes, patternsRes, techniquesRes] = await Promise.all([
          api.get(`/wiki/${userId}/pages`),
          api.get(`/wiki/${userId}/patterns`),
          api.get(`/wiki/${userId}/techniques`),
        ]);
        // Filter out "log" type pages — admin only
        setPages((pagesRes.pages || []).filter((p: WikiPage) => p.page_type !== "log"));
        setPatterns(patternsRes.patterns || []);
        setTechniques(techniquesRes.techniques || []);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Не удалось загрузить wiki";
        setError(msg);
      } finally {
        setLoading(false);
      }
    };

    fetchAll();
  }, [userId, role, router]);

  const loadPageContent = async (page: WikiPage) => {
    try {
      const res = await api.get(`/wiki/${userId}/pages/${page.page_path}`);
      setSelectedPage({ ...page, content: res.content });
    } catch {
      setSelectedPage({ ...page, content: "Не удалось загрузить содержимое" });
    }
  };

  if (loading) {
    return (
      <AuthLayout>
        <div className="flex h-[60vh] items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--accent)]" />
        </div>
      </AuthLayout>
    );
  }

  if (error) {
    return (
      <AuthLayout>
        <div className="mx-auto max-w-2xl px-4 py-12 text-center">
          <AlertTriangle className="mx-auto mb-4 h-12 w-12 text-[var(--warning)]" />
          <h2 className="mb-2 text-lg font-semibold text-[var(--text-primary)]">Wiki ещё не создана</h2>
          <p className="text-sm text-[var(--text-secondary)]">
            Завершите несколько тренировочных сессий — система автоматически создаст вашу персональную базу знаний.
          </p>
          <button
            onClick={() => router.push("/training")}
            className="mt-6 rounded-xl bg-[var(--accent)] px-6 py-2.5 text-sm font-medium text-white"
          >
            Начать тренировку
          </button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
    <div className="mx-auto max-w-5xl px-4 py-6">
      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <BackButton href="/home" />
        <BookOpen size={24} className="text-[var(--accent)]" />
        <h1 className="text-xl font-bold text-[var(--text-primary)]">Моя база знаний</h1>
      </div>

      {/* Stats row */}
      <div className="mb-6 grid grid-cols-3 gap-4">
        <div className="rounded-xl bg-[var(--bg-secondary)] p-4">
          <div className="text-2xl font-bold text-[var(--accent)]">{pages.length}</div>
          <div className="text-xs text-[var(--text-secondary)]">Страниц</div>
        </div>
        <div className="rounded-xl bg-[var(--bg-secondary)] p-4">
          <div className="text-2xl font-bold text-[var(--warning)]">{patterns.length}</div>
          <div className="text-xs text-[var(--text-secondary)]">Паттернов</div>
        </div>
        <div className="rounded-xl bg-[var(--bg-secondary)] p-4">
          <div className="text-2xl font-bold text-[var(--success)]">{techniques.length}</div>
          <div className="text-xs text-[var(--text-secondary)]">Техник</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 rounded-xl bg-[var(--bg-secondary)] p-1">
        {(["overview", "patterns", "techniques"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => { setTab(t); setSelectedPage(null); }}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              tab === t
                ? "bg-[var(--accent)] text-white"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {t === "overview" ? "Страницы" : t === "patterns" ? "Паттерны" : "Техники"}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === "overview" && !selectedPage && (
        <div className="space-y-2">
          {pages.length === 0 ? (
            <p className="py-8 text-center text-sm text-[var(--text-muted)]">
              База знаний ещё не создана. Знания появятся по мере тренировок.
            </p>
          ) : (
            pages.map((page) => (
              <motion.button
                key={page.page_path}
                onClick={() => loadPageContent(page)}
                className="w-full rounded-xl bg-[var(--bg-secondary)] p-4 text-left hover:bg-[var(--bg-tertiary)] transition-colors"
                whileTap={{ scale: 0.99 }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-[var(--text-primary)]">
                    {page.page_path.replace(/_/g, " ").replace(/\//g, " / ")}
                  </span>
                  <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-0.5 text-xs text-[var(--text-muted)]">
                    {page.page_type}
                  </span>
                </div>
                {page.tags.length > 0 && (
                  <div className="mt-2 flex gap-1">
                    {page.tags.map((tag) => (
                      <span key={tag} className="rounded bg-[var(--accent-muted)] px-2 py-0.5 text-xs text-[var(--accent)]">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </motion.button>
            ))
          )}
        </div>
      )}

      {tab === "overview" && selectedPage && (
        <div>
          <button
            onClick={() => setSelectedPage(null)}
            className="mb-4 flex items-center gap-1 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <ChevronLeft size={16} /> Назад к страницам
          </button>
          <div className="rounded-xl bg-[var(--bg-secondary)] p-6">
            <h2 className="mb-4 text-lg font-semibold text-[var(--text-primary)]">
              {selectedPage.page_path.replace(/_/g, " ").replace(/\//g, " / ")}
            </h2>
            <div className="prose prose-invert max-w-none text-sm text-[var(--text-secondary)] whitespace-pre-wrap">
              {selectedPage.content || "Пусто"}
            </div>
          </div>
        </div>
      )}

      {tab === "patterns" && (
        <div className="space-y-3">
          {patterns.length === 0 ? (
            <p className="py-8 text-center text-sm text-[var(--text-muted)]">
              Паттерны обнаруживаются автоматически после нескольких тренировок.
            </p>
          ) : (
            patterns.map((p) => {
              const cat = CATEGORY_LABELS[p.category] || CATEGORY_LABELS.quirk;
              const Icon = cat.icon;
              return (
                <div key={p.id} className="rounded-xl bg-[var(--bg-secondary)] p-4">
                  <div className="flex items-start gap-3">
                    <Icon size={18} style={{ color: cat.color }} className="mt-0.5 shrink-0" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[var(--text-primary)]">
                          {p.pattern_code.replace(/_/g, " ")}
                        </span>
                        <span
                          className="rounded-md px-2 py-0.5 text-xs font-medium"
                          style={{ color: cat.color, background: `${cat.color}15` }}
                        >
                          {cat.label}
                        </span>
                        {p.confirmed_at && (
                          <CheckCircle2 size={14} className="text-[var(--success)]" />
                        )}
                      </div>
                      <p className="mt-1 text-xs text-[var(--text-secondary)]">{p.description}</p>
                      <p className="mt-1 text-xs text-[var(--text-muted)]">
                        Обнаружено в {p.sessions_in_pattern} сессиях
                      </p>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {tab === "techniques" && (
        <div className="space-y-3">
          {techniques.length === 0 ? (
            <p className="py-8 text-center text-sm text-[var(--text-muted)]">
              Успешные техники сохраняются автоматически после высоких оценок.
            </p>
          ) : (
            techniques.map((t) => (
              <div key={t.id} className="rounded-xl bg-[var(--bg-secondary)] p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <TrendingUp size={16} className="text-[var(--success)]" />
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {t.technique_name}
                    </span>
                  </div>
                  <span className="text-sm font-bold" style={{
                    color: t.success_rate >= 0.7 ? "var(--success)" : t.success_rate >= 0.4 ? "var(--warning)" : "var(--danger)"
                  }}>
                    {Math.round(t.success_rate * 100)}%
                  </span>
                </div>
                <div className="mt-2 flex gap-4 text-xs text-[var(--text-muted)]">
                  <span>Успешно: {t.success_count}</span>
                  <span>Попыток: {t.attempt_count}</span>
                </div>
                {/* Success rate bar */}
                <div className="mt-2 h-1.5 w-full rounded-full bg-[var(--bg-tertiary)]">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.round(t.success_rate * 100)}%`,
                      background: t.success_rate >= 0.7 ? "var(--success)" : t.success_rate >= 0.4 ? "var(--warning)" : "var(--danger)",
                    }}
                  />
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
    </AuthLayout>
  );
}
