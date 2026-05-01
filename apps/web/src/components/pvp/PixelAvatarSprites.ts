/**
 * PixelAvatarSprites — 12 пиксельных портретов для арены БФЛ.
 *
 * ╔══════════════════════════════════════════════════════════════════════╗
 * ║   <<< THIS FILE IS THE ARTIST ZONE >>>                              ║
 * ║                                                                      ║
 * ║   Художник редактирует ТОЛЬКО строковые массивы в SPRITES ниже.     ║
 * ║   НЕ трогать: PixelAvatarLibrary.tsx (компонент, hook, mapping).    ║
 * ║                                                                      ║
 * ║   Любая ячейка 16×16 — один символ. Алфавит литералов:              ║
 * ║      .  прозрачный                                                   ║
 * ║      H  волосы / шапка тёмные      h  highlight волос               ║
 * ║      w  седина / белок глаза       S  кожа основная                 ║
 * ║      s  кожа тень / морщины        p  кожа бледная (уставшая)       ║
 * ║      o  кожа загорелая             e  глаз (зрачок)                 ║
 * ║      m  рот / губы                 n  шея                            ║
 * ║      B  основная одежда            b  тень одежды                    ║
 * ║      K  очень тёмная одежда        Z  оливковый (телогрейка)        ║
 * ║      Y  бежевый (халат, блузка)    R  приглушённый красный          ║
 * ║      g  золото (ордена, цепи)      c  холодное стекло (очки)        ║
 * ║      t  TIER ACCENT — ТОЛЬКО для player (бейдж/гарнитура)           ║
 * ║                                                                      ║
 * ║   ВАЖНО: client-спрайты НЕ должны содержать литерал `t`.            ║
 * ║   Тир клиента отображается через outline в FighterCard, не внутри.  ║
 * ║                                                                      ║
 * ║   Полное ТЗ: apps/web/src/styles/PIXEL_TOKENS.md §11.               ║
 * ╚══════════════════════════════════════════════════════════════════════╝
 *
 * 2026-05-01: первая версия — спрайты сделаны разработчиком по pixel-art
 * раскладкам из §11.5 ТЗ как функциональный baseline. Художник может
 * заменить любой массив на свою версию (16 строк по 16 символов каждая)
 * без изменения остального кода.
 */

import type { PixelAvatarCode } from "./PixelAvatarLibrary";

/* ╔════════════════════════════════════════════════════╗
   ║  PALETTE — ровно 18 цветов для 18 литералов.       ║
   ║  Художник может правки по hex'ам, но не добавлять  ║
   ║  новые литералы — это ломает SVG-рендер.           ║
   ╚════════════════════════════════════════════════════╝ */
export const PALETTE: Record<string, string> = {
  // Прозрачный — пропускается рендером
  ".": "transparent",
  // Волосы
  H: "#1a1a2e",
  h: "#3d3a52",
  w: "#d8d4c8",
  // Кожа
  S: "#e7c4a0",
  s: "#c79676",
  p: "#dcb898",
  o: "#a8714a",
  // Лицо
  e: "#0d0d18",
  m: "#9c4a4a",
  n: "#cfa57f",
  // Одежда
  B: "#5a5a6e",
  b: "#3a3a4e",
  K: "#26262e",
  Z: "#5a6a48",
  Y: "#aa8a6a",
  R: "#8a3838",
  // Спец-акценты
  g: "#d4a84b",
  c: "#5b9eff",
  // Tier accent — переопределяется компонентом во время рендера
  t: "var(--accent)",
};

/* ╔════════════════════════════════════════════════════╗
   ║   SPRITES — 12 портретов, каждый = 16 строк × 16   ║
   ║   символов. Художник: меняй только содержимое      ║
   ║   массивов, оставляя ключи.                        ║
   ╚════════════════════════════════════════════════════╝ */

/* ── PLAYER (4) ───────────────────────────────────── */

/** rookie — Стажёр БФЛ, 22-25, без гарнитуры, бейджик `t`. */
const SPRITE_ROOKIE: string[] = [
  "................",
  ".....HHHHHH.....",
  "....HhhhhhHH....",
  "...HhSSSSSSHh...",
  "..HhSSSSSSSSHh..",
  "..HSSSSSSSSSSh..",
  "..HSSeSSSSeSSh..",
  "..HSSSSSSSSSSh..",
  "..HSSppSSppSSh..",
  "..HSSSSmmSSSSh..",
  "...sSSSSSSSss...",
  "....sSSSSSss....",
  ".....nnnnnn.....",
  "....BBBBBBBBb...",
  "...BBBBtBBBBBb..",
  "..BBBBBBBBBBBBb.",
];

/** operator — Оператор колл-центра, 25-35, гарнитура+поло, default fallback. */
const SPRITE_OPERATOR: string[] = [
  "................",
  "................",
  "....HHHHHHHH....",
  "...HrhHHHHrhH...",
  "..HrSSSSSSSSrH..",
  "..HhSSSSSSSShH..",
  "..HhSeSSSSeShH..",
  "..HhSSSSSSSShH..",
  "..HhSSSmmSSShH..",
  "..HhSSSSSSSShH..",
  "...HhsSSSSshH...",
  "....hsSSSSsh....",
  ".....nnnnnn.....",
  "....bBBttBBb....",
  "...bBBBBBBBBb...",
  "..bBBBBBBBBBBb..",
];

/** senior — Старший менеджер, 30-40, очки+гарнитура+седина в висках. */
const SPRITE_SENIOR: string[] = [
  "................",
  "....HHHHHHHH....",
  "...HrhHwwHrhH...",
  "..HrSwSSSSwSrH..",
  "..HhSSSSSSSShH..",
  "..HtteSSSStteh..",
  "..HhSSSSSSSShH..",
  "..HhSSmmmmSShH..",
  "..HhsSSSSSSshH..",
  "..HhssSSSSsshH..",
  "....hsSSSSsh....",
  "....hssssssh....",
  ".....nnnnnn.....",
  "....bBBttBBb....",
  "...bBBBttBBBb...",
  "..bBBBBttBBBBb..",
];

/** lead — Тимлид, 35-45, без гарнитуры, пиджак, орденская планка. */
const SPRITE_LEAD: string[] = [
  "................",
  "....HwHHHwHH....",
  "...HwHwHwHwHH...",
  "..HhSSSSSSSShH..",
  "..HSSSSSSSSSSh..",
  "..HSSeSSSSeSSh..",
  "..HSSSSSSSSSSh..",
  "..HSSSmmmmSSSh..",
  "..HsSSSSSSSSsh..",
  "..HsSSSSSSSSsh..",
  "...sSSSSSSSss...",
  "....sSSSSSss....",
  ".....nnnnnn.....",
  "...KKKKttKKKbb..",
  "..KKKKgKKKKKKbb.",
  "..KKKKKKKKKKKbb.",
];

/* ── CLIENT — middle-aged (5) ─────────────────────── */

/** mother — Многодетная мама, 30-42, пучок волос, мешки под глазами. */
const SPRITE_MOTHER: string[] = [
  "......HHHH......",
  ".....HhhhhH.....",
  "....HHhhhhHH....",
  "...HhSSSSSSHh...",
  "..HhSSSSSSSSHh..",
  "..HSSSSSSSSSSh..",
  "..HSsseSSeessh..",
  "..HSSssssssSSh..",
  "..HSSSSSSSSSSh..",
  "..HSSSSmmSSSSh..",
  "...sSSSSSSSss...",
  "....sSSSSSss....",
  ".....nnnnnn.....",
  "....YYYYYYYYb...",
  "...YYsYYYYYpYb..",
  "..YYYYYYYYYYYbb.",
];

/** driver — Водитель такси/доставки, 28-45, кепка с лого, обветренное лицо. */
const SPRITE_DRIVER: string[] = [
  "................",
  "...HHHHHHHHHH...",
  "...HwwHHHHwwH...",
  "...HHHHHHHHHHH..",
  "...KKKKKKKKKK...",
  "..hhoooooooohh..",
  "..hoeooooooehh..",
  "..hooooooooohh..",
  "..hoosssssoosh..",
  "..hoooHmmHooooh.",
  "...soHHHHHHss...",
  "....sHHHHHHs....",
  ".....nnnnnn.....",
  "....KKKKKKKKb...",
  "..KKKKKKKKKKKb..",
  "..KKKKKKKKKKKbb.",
];

/** teacher — Учительница/бюджетник, 35-55, очки на цепочке, платок. */
const SPRITE_TEACHER: string[] = [
  "................",
  "....HwHHwwHH....",
  "...HhwHwwhHHh...",
  "..HhSSSSSSSSh...",
  "..HSSSSSSSSSSh..",
  "..HSccecceccSh..",
  "..HSScpppcSSSh..",
  "..HSSSSSSSSSSh..",
  "..HSSSmmmmSSSh..",
  "..HsSSSSSSSSsh..",
  "...sSSSSSSSss...",
  "....sSSSSSss....",
  "....RRRnnRRRR...",
  "...wRRwwwwRRwb..",
  "..wwwwwwwwwwwbb.",
  "..wwwwwwwwwwwbb.",
];

/** entrepreneur — Бывший ИП, 35-55, мятый пиджак, золотые часы. */
const SPRITE_ENTREPRENEUR: string[] = [
  "................",
  "....HHwHHwHH....",
  "...HhhHHhhHHh...",
  "..HhSSSSSSSSh...",
  "..HSSSSSSSSSSh..",
  "..HHHSeSSeSHHh..",
  "..HSSSSSSSSSSh..",
  "..HSSSSSSSSSSh..",
  "..HSHHsmmsHHSh..",
  "..HsHHHmmHHHsh..",
  "...sHHHHHHHHs...",
  "....sHHHHHHs....",
  ".....nnnnnn.....",
  "...KKKKKKKKKKb..",
  "..KKbKKKKbKKKbg.",
  "..KKKbKKKKKKKbg.",
];

/** single_man — Одинокий в депрессии, 35-50, щетина, бледность, опущенный взгляд. */
const SPRITE_SINGLE_MAN: string[] = [
  "................",
  "....HHHHHHHH....",
  "...HHHHHHHHHH...",
  "..HHpppppppppH..",
  "..HpsspppppspH..",
  "..Hppppspppph...",
  "..HppppeeppphH..",
  "..Hpsssssssph...",
  "..HpHHHHHpppHh..",
  "..HpHHHpmppHHh..",
  "...sHHHHHmHHs...",
  "....HHHHHHHs....",
  ".....nnnnnn.....",
  "...BBbBBbBBBBb..",
  "..BbBBbBBbBBBBb.",
  ".BBbBBBbBBBBBBbb",
];

/* ── CLIENT — senior 60+ (3) ──────────────────────── */

/** grandma — Бабушка-простушка, 65-78, платок в горошек, большие очки. */
const SPRITE_GRANDMA: string[] = [
  "....RRRRRRRR....",
  "...RwRRwRRwRR...",
  "..RRRwRRwRRwRR..",
  "..RwSSSSSSSSwR..",
  "..wpppppppppw...",
  "..wsssssssssw...",
  "..wccceppecccw..",
  "..wpcppppppcpw..",
  "..wppsspsspppw..",
  "..wppppmmppppw..",
  "...spsssmmsps...",
  "....RRRRRRRR....",
  ".....nnnnnn.....",
  "....YYYYYYYYb...",
  "...YYbYYYYYbYb..",
  "..YYYYYYYYYYYbb.",
];

/** grandpa_worker — Дед-работяга, 62-72, кепка, седые усы, телогрейка.
 *  2026-05-01: убрал заглавный `O` (был не в PALETTE — артефакт ручного
 *  набора). Теперь всё лицо использует один литерал `o` — обветренная кожа. */
const SPRITE_GRANDPA_WORKER: string[] = [
  "................",
  "...BBBBBBBBBB...",
  "..BBBBBBBBBBBB..",
  "..wBBBBBBBBBBw..",
  "..wKKKKKKKKKKw..",
  "..oooooooooooo..",
  "..oooosspooooo..",
  "..ooeoooooeooo..",
  "..ooosssssoooo..",
  "..oowwwwwwwwoo..",
  "..oooommmmoooo..",
  "...sssoooosss...",
  ".....nnnnnn.....",
  "...ZZZZZZZZZZb..",
  "..ZZbZZZZZbZZZb.",
  ".ZZZZZZZZZZZZZbb",
];

/** vet — Военный пенсионер, 65-75, ёжик, седые усы, орденская планка. */
const SPRITE_VET: string[] = [
  "................",
  "....wHwHwHwH....",
  "...wHwHwHwHHw...",
  "..hwppppppppwh..",
  "..wppppppppppw..",
  "..wppeppppeppw..",
  "..wppppppppppw..",
  "..wppwwwwwwppw..",
  "..wpppmmmppppw..",
  "..wppspssspspw..",
  "...sppppppps....",
  "....wwppppww....",
  "....wwwnnwww....",
  "...KKKKwwKKKKb..",
  "..KKRgcRgcKKKbb.",
  "..KKKKKKKKKKKbb.",
];

/* ╔════════════════════════════════════════════════════╗
   ║   EXPORT MAP — единый словарь для PixelPortrait.   ║
   ║   Если художник добавляет новый код, нужно:        ║
   ║   1) добавить в PixelAvatarCode (Library.tsx)       ║
   ║   2) добавить в эту карту                           ║
   ║   3) обновить ARCHETYPE_TO_AVATAR (Library.tsx)     ║
   ╚════════════════════════════════════════════════════╝ */
export const SPRITES: Record<PixelAvatarCode, string[]> = {
  rookie: SPRITE_ROOKIE,
  operator: SPRITE_OPERATOR,
  senior: SPRITE_SENIOR,
  lead: SPRITE_LEAD,
  mother: SPRITE_MOTHER,
  driver: SPRITE_DRIVER,
  teacher: SPRITE_TEACHER,
  entrepreneur: SPRITE_ENTREPRENEUR,
  single_man: SPRITE_SINGLE_MAN,
  grandma: SPRITE_GRANDMA,
  grandpa_worker: SPRITE_GRANDPA_WORKER,
  vet: SPRITE_VET,
};
