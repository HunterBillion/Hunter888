"use client";

/**
 * StageSelect — sticky якорная навигация по секциям /leaderboard.
 *
 * 2026-05-08 — часть аркадного редизайна. Заменяет старые табы pill-стиля.
 * Рисует «ВЫБОР АРЕНЫ» — горизонтальный пиксельный пульт с 4 кнопками.
 * При скролле прилипает к верху, активная секция подсвечивается через
 * IntersectionObserver. Клик → плавный скролл к якорю #stage-<id>.
 *
 * Геометрия:
 *   - sticky top: 0 (под глобальной шапкой Hunter888 — она fixed/blur,
 *     pixel-pill начинается прямо под ней)
 *   - высота 56px — достаточно для 14px шрифта + padding
 *   - на mobile одной строкой со скроллом overflow-x
 *   - бордер 2px пикселями + glow при активной кнопке
 */

import { useEffect, useRef, useState } from "react";
import { Trophy, Crown, Building2, Swords, type LucideIcon } from "lucide-react";

interface Stage {
  id: string;
  numeral: string;
  label: string;
  icon: LucideIcon;
  accent: string;
}

const STAGES: Stage[] = [
  { id: "league", numeral: "I", label: "ЛИГА", icon: Trophy, accent: "var(--accent)" },
  { id: "company", numeral: "II", label: "КОМПАНИЯ", icon: Crown, accent: "#facc15" },
  { id: "teams", numeral: "III", label: "КОМАНДЫ", icon: Building2, accent: "#fb923c" },
  { id: "duels", numeral: "IV", label: "ДУЭЛИ", icon: Swords, accent: "#ff3ec8" },
];

/** Читаем hash при первом рендере, чтобы при заходе на
 *  `/leaderboard#stage-duels` сразу подсветить Дуэли (а не Лигу).
 *  Без этого пользователь видит «Лига» подсвеченной 1 кадр пока
 *  IntersectionObserver не обновит state — некрасивая визуальная
 *  заминка, особенно после редиректа с /pvp/leaderboard.
 */
function readInitialActive(): string {
  if (typeof window === "undefined") return "league";
  const hash = window.location.hash.replace(/^#stage-/, "");
  if (["league", "company", "teams", "duels"].includes(hash)) return hash;
  return "league";
}

export function StageSelect() {
  const [active, setActive] = useState<string>(readInitialActive);
  const isProgrammaticScrollRef = useRef(false);

  // 2026-05-08: при заходе с hash в URL (после редиректа с
  // /pvp/leaderboard или из шара ссылки) — программно скроллим к
  // секции на mount. Браузер обычно делает это автоматически, но не
  // учитывает sticky-навбар и упирает якорь под него.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash.replace(/^#stage-/, "");
    if (!["league", "company", "teams", "duels"].includes(hash)) return;
    if (hash === "league") return; // дефолт — секция и так наверху
    // Дать DOM время отрисовать секции, потом скроллим.
    const t = window.setTimeout(() => {
      const target = document.getElementById(`stage-${hash}`);
      if (target) {
        isProgrammaticScrollRef.current = true;
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        window.setTimeout(() => {
          isProgrammaticScrollRef.current = false;
        }, 800);
      }
    }, 80);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(() => {
    // IntersectionObserver: пометить активной секцию, чья
    // STAGE-divider в данный момент в верхней половине экрана.
    const targets = STAGES.map((s) => document.getElementById(`stage-${s.id}`)).filter(
      (el): el is HTMLElement => el !== null,
    );
    if (targets.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (isProgrammaticScrollRef.current) return;
        // Пик в верхней половине viewport'а (rootMargin учитывает sticky)
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]) {
          const id = visible[0].target.id.replace(/^stage-/, "");
          setActive(id);
        }
      },
      {
        // Ловим пересечение в зоне 110px-50% — учитывает sticky-навбар (56px)
        // + основная шапка Hunter888 (~56px).
        rootMargin: "-112px 0px -50% 0px",
        threshold: [0, 0.25, 0.5, 0.75, 1],
      },
    );
    targets.forEach((t) => observer.observe(t));
    return () => observer.disconnect();
  }, []);

  const scrollTo = (id: string) => {
    const target = document.getElementById(`stage-${id}`);
    if (!target) return;
    isProgrammaticScrollRef.current = true;
    setActive(id);
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    // 2026-05-08: синхронизируем URL hash с активной секцией. Это даёт:
    // (1) можно копировать ссылку — она откроется на нужной секции;
    // (2) кнопка «назад» в браузере возвращает к предыдущей секции;
    // (3) внешние редиректы (как с /pvp/leaderboard) попадают точно
    //     в нужный таб без потери контекста.
    // history.replaceState не вызывает scroll и не пингует роутер
    // Next.js — это то что нужно.
    if (typeof window !== "undefined") {
      const newUrl = id === "league"
        ? window.location.pathname
        : `${window.location.pathname}#stage-${id}`;
      window.history.replaceState(null, "", newUrl);
    }
    // Снять флаг через 800ms — этого хватает для smooth-scroll до конца.
    window.setTimeout(() => {
      isProgrammaticScrollRef.current = false;
    }, 800);
  };

  return (
    <div
      className="sticky top-0 z-30 -mx-4 px-4 py-3"
      style={{
        background: "linear-gradient(to bottom, rgba(8,5,18,0.95) 0%, rgba(8,5,18,0.85) 80%, transparent 100%)",
        backdropFilter: "blur(8px)",
      }}
    >
      <div
        className="text-center font-pixel uppercase tracking-widest mb-2"
        style={{
          color: "var(--text-muted)",
          fontSize: "14px",
        }}
      >
        ▰ ВЫБОР АРЕНЫ ▰
      </div>
      <div className="flex justify-center">
        <div
          className="inline-flex gap-1.5 p-1.5 rounded-md max-w-full overflow-x-auto"
          style={{
            background: "rgba(8,5,18,0.9)",
            border: "2px solid rgba(255,255,255,0.12)",
            boxShadow: "inset 0 0 12px rgba(0,0,0,0.5)",
          }}
        >
          {STAGES.map((stage) => {
            const Icon = stage.icon;
            const isActive = active === stage.id;
            return (
              <button
                key={stage.id}
                type="button"
                onClick={() => scrollTo(stage.id)}
                aria-current={isActive ? "true" : undefined}
                className="font-pixel uppercase tracking-widest inline-flex items-center gap-2 px-3 md:px-4 py-2 rounded-sm shrink-0 transition-all"
                style={{
                  // ≥14px — требование пользователя.
                  fontSize: "15px",
                  background: isActive ? stage.accent : "transparent",
                  color: isActive ? "#0b0b14" : stage.accent,
                  border: `2px solid ${stage.accent}`,
                  boxShadow: isActive
                    ? `0 0 14px ${stage.accent}, inset 0 0 6px rgba(0,0,0,0.25)`
                    : "none",
                }}
              >
                <Icon size={16} />
                <span>
                  <span aria-hidden style={{ opacity: 0.65, marginRight: 6 }}>
                    {stage.numeral}
                  </span>
                  {stage.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
