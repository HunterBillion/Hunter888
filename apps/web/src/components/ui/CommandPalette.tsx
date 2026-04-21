"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import {
  Search,
  Home,
  BarChart3,
  Users,
  History,
  Settings,
  Trophy,
  Swords,
  Mic,
  FileBarChart,
  Bell,
  BookOpen,
  ArrowRight,
  Shield,
} from "lucide-react";
import { useFocusTrap } from "@/hooks/useFocusTrap";
import { useAuth } from "@/hooks/useAuth";
import { hasRole } from "@/lib/guards";

interface CommandItem {
  id: string;
  label: string;
  description?: string;
  icon: typeof Home;
  href?: string;
  action?: () => void;
  keywords: string[];
  /** Only show for certain roles */
  roles?: string[];
}

const RECENT_KEY = "vh_cmd_recent";
const MAX_RECENT = 5;

function getRecentIds(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function saveRecent(id: string) {
  try {
    const ids = getRecentIds().filter((i) => i !== id);
    ids.unshift(id);
    localStorage.setItem(RECENT_KEY, JSON.stringify(ids.slice(0, MAX_RECENT)));
  } catch { /* localStorage unavailable */ }
}

const COMMANDS: CommandItem[] = [
  { id: "home", label: "Главная", description: "Дашборд менеджера", icon: Home, href: "/home", keywords: ["главная", "home", "дашборд"] },
  { id: "training", label: "Начать тренировку", description: "Выбрать сценарий", icon: Mic, href: "/training", keywords: ["тренировка", "training", "сценарий", "практика"] },
  { id: "pvp", label: "PvP Арена", description: "Бой с другим игроком", icon: Swords, href: "/pvp", keywords: ["pvp", "арена", "бой", "дуэль", "соперник"] },
  { id: "history", label: "История тренировок", description: "Все сессии", icon: History, href: "/history", keywords: ["история", "history", "сессии", "прошлые"] },
  { id: "analytics", label: "Аналитика", description: "Статистика и прогресс", icon: BarChart3, href: "/analytics", keywords: ["аналитика", "analytics", "статистика", "прогресс", "графики"] },
  { id: "leaderboard", label: "Рейтинг", description: "Таблица лидеров", icon: Trophy, href: "/leaderboard", keywords: ["рейтинг", "leaderboard", "лидеры", "топ"] },
  { id: "clients", label: "CRM Клиенты", description: "Управление клиентами", icon: Users, href: "/clients", keywords: ["клиенты", "clients", "crm", "контакты"] },
  { id: "knowledge", label: "База знаний", description: "Квизы и материалы", icon: BookOpen, href: "/pvp?tab=knowledge", keywords: ["знания", "knowledge", "квиз", "тест", "обучение"] },
  { id: "reports", label: "Отчёты", description: "Командные отчёты (в Панели РОП)", icon: FileBarChart, href: "/dashboard?tab=reports", keywords: ["отчёты", "reports", "команда"], roles: ["rop", "admin"] },
  { id: "notifications", label: "Уведомления", icon: Bell, href: "/notifications", keywords: ["уведомления", "notifications", "оповещения"] },
  { id: "settings", label: "Настройки", description: "Тема, звук, профиль", icon: Settings, href: "/settings", keywords: ["настройки", "settings", "тема", "профиль"] },
  { id: "dashboard", label: "Панель управления", description: "Обзор команды (РОП)", icon: Shield, href: "/dashboard", keywords: ["панель", "dashboard", "управление", "роп"], roles: ["rop", "admin"] },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const router = useRouter();
  const { user } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const trapRef = useFocusTrap(open, () => setOpen(false));

  // Filter commands by query and role
  const filtered = COMMANDS.filter((cmd) => {
    // Role check
    if (cmd.roles && user && !hasRole(user, cmd.roles as import("@/types").UserRole[])) return false;
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      cmd.label.toLowerCase().includes(q) ||
      cmd.description?.toLowerCase().includes(q) ||
      cmd.keywords.some((k) => k.includes(q))
    );
  });

  // Reset selection on query change
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Cmd+K / Ctrl+K to toggle
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Focus input on open
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const execute = useCallback(
    (cmd: CommandItem) => {
      setOpen(false);
      saveRecent(cmd.id);
      if (cmd.href) router.push(cmd.href);
      else if (cmd.action) cmd.action();
    },
    [router],
  );

  // Build display list: recent items first when query is empty
  const recentIds = useMemo(() => (open ? getRecentIds() : []), [open]);
  const recentItems = useMemo(() => {
    if (query.trim()) return [];
    return recentIds
      .map((id) => filtered.find((c) => c.id === id))
      .filter((c): c is CommandItem => c !== undefined);
  }, [query, recentIds, filtered]);
  const hasRecent = recentItems.length > 0;
  // Remove recent items from main list to avoid duplication
  const mainItems = hasRecent
    ? filtered.filter((c) => !recentIds.includes(c.id))
    : filtered;
  const displayItems = hasRecent ? [...recentItems, ...mainItems] : filtered;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, displayItems.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && displayItems[selectedIndex]) {
      e.preventDefault();
      execute(displayItems[selectedIndex]);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[300] flex items-start justify-center pt-[15vh]"
          style={{ background: "var(--overlay-bg)", backdropFilter: "blur(4px)" }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            ref={trapRef}
            initial={{ scale: 0.95, y: -10 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.95, y: -10 }}
            transition={{ type: "spring", stiffness: 500, damping: 35 }}
            className="w-full max-w-lg mx-4 overflow-hidden rounded-2xl"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              boxShadow: "0 25px 60px rgba(0,0,0,0.5)",
            }}
            role="dialog"
            aria-modal="true"
            aria-label="Поиск по приложению"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Search input */}
            <div
              className="flex items-center gap-3 px-4 py-3"
              style={{ borderBottom: "1px solid var(--border-color)" }}
            >
              <Search size={18} style={{ color: "var(--text-muted)" }} />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Поиск страницы или действия..."
                className="flex-1 bg-transparent text-sm outline-none"
                style={{ color: "var(--text-primary)" }}
                aria-label="Поиск"
                autoComplete="off"
              />
              <kbd
                className="hidden sm:inline-flex items-center justify-center px-1.5 h-5 rounded font-mono text-xs"
                style={{
                  background: "var(--bg-tertiary)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-muted)",
                }}
              >
                ESC
              </kbd>
            </div>

            {/* Results */}
            <div className="max-h-[40vh] overflow-y-auto py-2">
              {displayItems.length === 0 ? (
                <div className="px-4 py-8 text-center text-xs" style={{ color: "var(--text-muted)" }}>
                  Ничего не найдено
                </div>
              ) : (
                <>
                  {hasRecent && (
                    <div className="px-4 pt-1 pb-1.5 font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                      Недавние
                    </div>
                  )}
                  {displayItems.map((cmd, i) => {
                    const Icon = cmd.icon;
                    const isSelected = i === selectedIndex;
                    const showSeparator = hasRecent && i === recentItems.length;
                    return (
                      <div key={cmd.id}>
                        {showSeparator && (
                          <div className="px-4 pt-2.5 pb-1.5 font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)", borderTop: "1px solid var(--border-color)" }}>
                            Все
                          </div>
                        )}
                        <button
                          className="w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors"
                          style={{
                            background: isSelected ? "var(--accent-muted)" : "transparent",
                          }}
                          onClick={() => execute(cmd)}
                          onMouseEnter={() => setSelectedIndex(i)}
                        >
                          <div
                            className="flex h-8 w-8 items-center justify-center rounded-lg shrink-0"
                            style={{
                              background: isSelected ? "var(--accent)" : "var(--input-bg)",
                            }}
                          >
                            <Icon size={14} style={{ color: isSelected ? "white" : "var(--text-muted)" }} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                              {cmd.label}
                            </div>
                            {cmd.description && (
                              <div className="text-xs truncate" style={{ color: "var(--text-muted)" }}>
                                {cmd.description}
                              </div>
                            )}
                          </div>
                          {isSelected && (
                            <ArrowRight size={12} style={{ color: "var(--accent)" }} />
                          )}
                        </button>
                      </div>
                    );
                  })}
                </>
              )}
            </div>

            {/* Footer hint */}
            <div
              className="flex items-center justify-between px-4 py-2 text-xs font-mono"
              style={{ borderTop: "1px solid var(--border-color)", color: "var(--text-muted)" }}
            >
              <span>↑↓ навигация · Enter выбрать · Esc закрыть</span>
              <span>⌘K</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
