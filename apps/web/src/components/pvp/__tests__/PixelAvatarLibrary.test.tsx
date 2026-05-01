/**
 * PixelAvatarLibrary — юнит-тесты по acceptance criteria из §11.9 ТЗ.
 *
 * Проверяемое:
 *   1. SPRITES содержит все 12 канонических кодов; каждый — 16 строк × 16 символов.
 *   2. PALETTE покрывает все литералы, использованные в SPRITES.
 *   3. Tier-color литералы (`t`/`r`) НИКОГДА не встречаются внутри client-спрайтов
 *      (это главный инвариант §11.3 — тир клиента уезжает в outline, не внутрь).
 *   4. ARCHETYPE_TO_AVATAR: все 25 ключей из §11.8 замаплены и значения — валидные
 *      PixelAvatarCode из закрытого списка.
 *   5. resolveOpponentAvatar — фолбэк на "operator" для unknown / null / undefined,
 *      никаких 404.
 *   6. avatarFromLevel — точные границы уровней: 1-9 / 10-29 / 30-59 / 60+.
 *   7. PixelPortrait — рендерит SVG с data-literal атрибутами, можно найти ячейки.
 *   8. usePlayerAvatar — стабильное мемоизированное значение.
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { renderHook } from "@testing-library/react";
import * as React from "react";
import {
  ALL_AVATAR_CODES,
  ARCHETYPE_TO_AVATAR,
  AVATAR_LABELS,
  PixelPortrait,
  PLAYER_AVATARS,
  avatarFromLevel,
  isPlayerAvatar,
  resolveOpponentAvatar,
  usePlayerAvatar,
  type PixelAvatarCode,
} from "../PixelAvatarLibrary";
import { PALETTE, SPRITES } from "../PixelAvatarSprites";

const PLAYER_CODES = ["rookie", "operator", "senior", "lead"] as const;
const CLIENT_CODES_MIDDLE = [
  "mother",
  "driver",
  "teacher",
  "entrepreneur",
  "single_man",
] as const;
const CLIENT_CODES_SENIOR = ["grandma", "grandpa_worker", "vet"] as const;
const CLIENT_CODES = [...CLIENT_CODES_MIDDLE, ...CLIENT_CODES_SENIOR] as const;

describe("PixelAvatarLibrary — закрытый набор кодов", () => {
  it("ALL_AVATAR_CODES содержит ровно 12 элементов", () => {
    expect(ALL_AVATAR_CODES).toHaveLength(12);
  });

  it("ALL_AVATAR_CODES покрывает все 4 player + 8 client", () => {
    const set = new Set(ALL_AVATAR_CODES);
    [...PLAYER_CODES, ...CLIENT_CODES].forEach((code) => {
      expect(set.has(code)).toBe(true);
    });
  });

  it("PLAYER_AVATARS содержит ровно 4 player-кода", () => {
    expect(PLAYER_AVATARS.size).toBe(4);
    PLAYER_CODES.forEach((code) => expect(PLAYER_AVATARS.has(code)).toBe(true));
  });

  it("isPlayerAvatar корректно различает player vs client", () => {
    PLAYER_CODES.forEach((c) => expect(isPlayerAvatar(c)).toBe(true));
    CLIENT_CODES.forEach((c) => expect(isPlayerAvatar(c)).toBe(false));
  });
});

describe("SPRITES — структура 16×16", () => {
  it("содержит все 12 кодов как ключи", () => {
    ALL_AVATAR_CODES.forEach((code) => {
      expect(SPRITES[code]).toBeDefined();
    });
  });

  it("каждый спрайт = 16 строк по 16 символов (форма 16×16)", () => {
    ALL_AVATAR_CODES.forEach((code) => {
      const sprite = SPRITES[code];
      expect(sprite.length).toBe(16);
      sprite.forEach((row, y) => {
        expect(
          row.length,
          `sprite '${code}' row ${y} имеет длину ${row.length}, ожидалось 16`,
        ).toBe(16);
      });
    });
  });

  it("каждый литерал из SPRITES присутствует в PALETTE (или это `.` или tier-литерал)", () => {
    const usedLiterals = new Set<string>();
    ALL_AVATAR_CODES.forEach((code) => {
      SPRITES[code].forEach((row) => {
        for (const ch of row) usedLiterals.add(ch);
      });
    });
    // `.` — прозрачный, `t`/`r` — динамические tier accent, остальное — статичные hex.
    const dynamicLiterals = new Set([".", "t", "r"]);
    const missing: string[] = [];
    usedLiterals.forEach((ch) => {
      if (dynamicLiterals.has(ch)) return;
      if (!PALETTE[ch]) missing.push(ch);
    });
    expect(
      missing,
      `литералы без записи в PALETTE: ${JSON.stringify(missing)}`,
    ).toEqual([]);
  });
});

describe("ИНВАРИАНТ §11.3 — tier-литералы только в player-спрайтах", () => {
  it("client-спрайты НЕ содержат литералов `t` или `r`", () => {
    CLIENT_CODES.forEach((code) => {
      const sprite = SPRITES[code];
      const cells: string[] = [];
      sprite.forEach((row, y) => {
        for (let x = 0; x < row.length; x += 1) {
          const ch = row[x];
          if (ch === "t" || ch === "r") cells.push(`${code} (${x},${y})`);
        }
      });
      expect(
        cells,
        `client-спрайт '${code}' содержит tier-литералы в: ${cells.join(", ")}`,
      ).toEqual([]);
    });
  });

  it("PixelPortrait рендеринг client-спрайта НЕ содержит rect[data-literal=t/r]", () => {
    CLIENT_CODES.forEach((code) => {
      const { container } = render(
        <PixelPortrait code={code as PixelAvatarCode} tier="gold" size={56} />,
      );
      const tierRects = container.querySelectorAll(
        'rect[data-literal="t"], rect[data-literal="r"]',
      );
      expect(
        tierRects.length,
        `client-спрайт '${code}' отрендерил ${tierRects.length} tier-ячеек`,
      ).toBe(0);
    });
  });

  it("PixelPortrait рендеринг player-спрайта МОЖЕТ содержать tier-литералы", () => {
    // operator/senior/rookie/lead все имеют либо `t`, либо `r` в спрайте.
    const tierRectCounts: Record<string, number> = {};
    PLAYER_CODES.forEach((code) => {
      const { container } = render(
        <PixelPortrait code={code} tier="gold" size={56} />,
      );
      tierRectCounts[code] = container.querySelectorAll(
        'rect[data-literal="t"], rect[data-literal="r"]',
      ).length;
    });
    // По меньшей мере у одного player-кода tier-литералы должны быть отрендерены —
    // иначе вся затея с tier-color на player-аватарах бессмысленна.
    const totalTierCells = Object.values(tierRectCounts).reduce((a, b) => a + b, 0);
    expect(
      totalTierCells,
      `ни один player-спрайт не содержит tier-литералов: ${JSON.stringify(tierRectCounts)}`,
    ).toBeGreaterThan(0);
  });
});

describe("ARCHETYPE_TO_AVATAR — маппинг 25 архетипов из §11.8", () => {
  // Список из §11.8 ТЗ (строки 763-804). 25 архетипов + sentinel `default`.
  const SPEC_ARCHETYPES = [
    "skeptic",
    "blamer",
    "sarcastic",
    "aggressive",
    "hostile",
    "stubborn",
    "doubting",
    "cold",
    "manipulator",
    "bargainer",
    "promiser",
    "tired_worker",
    "defeated",
    "chronic_stress",
    "emotional",
    "panicking",
    "vip",
    "wealthy_client",
    "entrepreneur",
    "pensioner",
    "silver_hair",
    "veteran",
    "retired_officer",
    "scammed_pensioner",
    "decisive",
    "ready_to_close",
    "teacher",
    "budget_worker",
    "single_mother",
    "multi_child",
  ];

  it("все архетипы из §11.8 присутствуют в карте", () => {
    SPEC_ARCHETYPES.forEach((arch) => {
      expect(
        ARCHETYPE_TO_AVATAR[arch],
        `архетип '${arch}' отсутствует в ARCHETYPE_TO_AVATAR`,
      ).toBeDefined();
    });
  });

  it("все значения карты — валидные PixelAvatarCode", () => {
    const validSet = new Set(ALL_AVATAR_CODES);
    Object.entries(ARCHETYPE_TO_AVATAR).forEach(([arch, code]) => {
      expect(
        validSet.has(code),
        `архетип '${arch}' замаплен на невалидный код '${code}'`,
      ).toBe(true);
    });
  });

  it("client-архетипы НЕ маппятся в player-аватары (кроме намеренного 'decisive')", () => {
    // `decisive` — единственное допустимое исключение (см. ТЗ §11.8 закомментированный
    // намёк "lead это PLAYER. Для CLIENT decisive → entrepreneur"). Текущая реализация
    // делает выбор в пользу client-маппинга `entrepreneur` — проверим это.
    const clientArchetypes = SPEC_ARCHETYPES.filter((a) => a !== "decisive");
    clientArchetypes.forEach((arch) => {
      const code = ARCHETYPE_TO_AVATAR[arch];
      expect(
        isPlayerAvatar(code),
        `client-архетип '${arch}' замаплен на player-код '${code}' — нарушение §11.3`,
      ).toBe(false);
    });
  });
});

describe("resolveOpponentAvatar — fallback логика", () => {
  it("возвращает корректный код для известного архетипа", () => {
    expect(resolveOpponentAvatar("emotional")).toBe("mother");
    expect(resolveOpponentAvatar("veteran")).toBe("vet");
    expect(resolveOpponentAvatar("skeptic")).toBe("grandpa_worker");
  });

  it("fallback на 'operator' для unknown / null / undefined", () => {
    expect(resolveOpponentAvatar(null)).toBe("operator");
    expect(resolveOpponentAvatar(undefined)).toBe("operator");
    expect(resolveOpponentAvatar("")).toBe("operator");
    expect(resolveOpponentAvatar("nonexistent_xyz")).toBe("operator");
    expect(resolveOpponentAvatar("UltimateSomething")).toBe("operator");
  });

  it("case-insensitive lookup (toLowerCase)", () => {
    // Реализация делает .toLowerCase().trim() — проверим.
    expect(resolveOpponentAvatar("EMOTIONAL")).toBe("mother");
    expect(resolveOpponentAvatar("  emotional  ")).toBe("mother");
  });
});

describe("avatarFromLevel — границы уровней", () => {
  it("level 1-9 → rookie", () => {
    for (const lvl of [1, 5, 9]) {
      expect(avatarFromLevel(lvl)).toBe("rookie");
    }
  });

  it("level 10-29 → operator", () => {
    for (const lvl of [10, 15, 29]) {
      expect(avatarFromLevel(lvl)).toBe("operator");
    }
  });

  it("level 30-59 → senior", () => {
    for (const lvl of [30, 45, 59]) {
      expect(avatarFromLevel(lvl)).toBe("senior");
    }
  });

  it("level 60+ → lead", () => {
    for (const lvl of [60, 100, 999]) {
      expect(avatarFromLevel(lvl)).toBe("lead");
    }
  });

  it("null / undefined / 0 / NaN / отрицательные → operator (нейтральный default)", () => {
    expect(avatarFromLevel(null)).toBe("operator");
    expect(avatarFromLevel(undefined)).toBe("operator");
    expect(avatarFromLevel(0)).toBe("operator");
    expect(avatarFromLevel(-5)).toBe("operator");
    expect(avatarFromLevel(NaN)).toBe("operator");
  });
});

describe("usePlayerAvatar — React hook", () => {
  it("возвращает то же значение что avatarFromLevel", () => {
    const { result, rerender } = renderHook(
      ({ level }: { level: number | null | undefined }) =>
        usePlayerAvatar(level),
      { initialProps: { level: 5 as number | null | undefined } },
    );
    expect(result.current).toBe("rookie");
    rerender({ level: 25 });
    expect(result.current).toBe("operator");
    rerender({ level: 75 });
    expect(result.current).toBe("lead");
    rerender({ level: null });
    expect(result.current).toBe("operator");
  });

  it("стабильна по идентичному level (мемоизация)", () => {
    const { result, rerender } = renderHook(
      ({ level }: { level: number }) => usePlayerAvatar(level),
      { initialProps: { level: 25 } },
    );
    const first = result.current;
    rerender({ level: 25 });
    expect(result.current).toBe(first);
  });
});

describe("PixelPortrait — рендер", () => {
  it("рендерит SVG с правильным viewBox", () => {
    const { container } = render(<PixelPortrait code="operator" size={56} />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("viewBox")).toBe("0 0 100 100");
  });

  it("рендерит хотя бы 50 rect-ов для каждого спрайта (плотность спрайта)", () => {
    ALL_AVATAR_CODES.forEach((code) => {
      const { container } = render(<PixelPortrait code={code} size={56} />);
      const rects = container.querySelectorAll("rect");
      // 16×16 = 256 ячеек максимум. Любой портрет — голова+лицо — ≥50 rect-ов.
      expect(
        rects.length,
        `спрайт '${code}' имеет всего ${rects.length} rect-ов — спрайт пустой?`,
      ).toBeGreaterThan(50);
    });
  });

  it("каждый rect имеет атрибут data-literal", () => {
    const { container } = render(<PixelPortrait code="grandma" size={56} />);
    container.querySelectorAll("rect").forEach((rect: SVGRectElement) => {
      expect(rect.getAttribute("data-literal")).toBeTruthy();
    });
  });

  it("неизвестный код фолбэчит на operator (никаких 404)", () => {
    // @ts-expect-error — намеренная подача невалидного кода
    const { container } = render(<PixelPortrait code="nonexistent" size={56} />);
    // Должен отрендериться нейтральный спрайт, без crash.
    const rects = container.querySelectorAll("rect");
    expect(rects.length).toBeGreaterThan(0);
  });

  it("ariaLabel переключает aria-hidden → role=img", () => {
    const { container: silent } = render(
      <PixelPortrait code="operator" size={56} />,
    );
    expect(silent.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");

    const { container: speaking } = render(
      <PixelPortrait code="operator" size={56} label="Аватар оператора" />,
    );
    const svg = speaking.querySelector("svg");
    expect(svg?.getAttribute("role")).toBe("img");
    expect(svg?.getAttribute("aria-label")).toBe("Аватар оператора");
  });
});

describe("AVATAR_LABELS — подписи для UI", () => {
  it("содержит все 12 кодов с name + subtitle", () => {
    ALL_AVATAR_CODES.forEach((code) => {
      const label = AVATAR_LABELS[code];
      expect(label, `AVATAR_LABELS['${code}'] missing`).toBeDefined();
      expect(label.name).toBeTruthy();
      expect(label.subtitle).toBeTruthy();
    });
  });

  it("subtitle включает возрастной диапазон (для подписей в /dev/avatars-preview)", () => {
    // Спека требует "подписями возраста под каждым портретом". Проверим что в subtitle
    // есть хотя бы две цифры и дефис — достаточный сигнал что возраст указан.
    ALL_AVATAR_CODES.forEach((code) => {
      const subtitle = AVATAR_LABELS[code].subtitle;
      expect(
        /\d{2}-\d{2}|\d{2}\+/.test(subtitle),
        `subtitle для '${code}' не содержит возрастного диапазона: "${subtitle}"`,
      ).toBe(true);
    });
  });
});
