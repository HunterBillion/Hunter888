/**
 * PixelMascotSprites — 16×16 chunky-pixel маскот-лев для PvP лобби.
 *
 * Спрайты сгенерированы через скрипт (см. /tmp/gen_lion.js) и валидированы:
 * каждая строка ровно 16 символов, выбран замкнутый алфавит литералов:
 *
 *   .  transparent
 *   M  mane (тёмный коричневый)
 *   m  mane (средний коричневый)
 *   F  face fur (золотой яркий)
 *   f  body fur (золотой средний)
 *   s  skin / muzzle (светлый кремовый)
 *   e  eye (чёрный)
 *   n  nose / sad-mouth (тёмно-коричневый)
 *   w  tooth / mouth glint (белый)
 *   g  accent — заменяется на проп `accent` (sparkle / Z / tear)
 *
 * Стиль и формат идентичны PixelAvatarSprites.ts / PixelIcon.tsx:
 *   - сетка 16 строк × 16 символов
 *   - один char = 1 ячейка SVG `<rect width=1 height=1>`
 *   - `image-rendering: pixelated`
 */

export type MascotState = "idle" | "walk" | "cheer" | "sad" | "sleep";

export const PALETTE: Record<string, string> = {
  M: "#3a2410",
  m: "#5c3a1d",
  F: "#e89a3a",
  f: "#c47a25",
  s: "#f5d8a8",
  e: "#1a0f08",
  n: "#241612",
  w: "#ffffff",
};

const idle0: string[] = [
  "....M......M....",
  "...MMM....MMM...",
  "..MMMMMMMMMMMM..",
  ".MMmmmmmmmmmmMM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFsessssesFmmM",
  "MmmFssssssssFmmM",
  "MmmFssnnnnssFmmM",
  "MmmFsswwwwssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  ".....ff..ff.....",
  "................",
];

const idle1: string[] = [
  "....M......M....",
  "...MMM....MMM...",
  "..MMMMMMMMMMMM..",
  ".MMmmmmmmmmmmMM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFssssssssFmmM",
  "MmmFssssssssFmmM",
  "MmmFssnnnnssFmmM",
  "MmmFsswwwwssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  ".....ff..ff.....",
  "................",
];

const idle2: string[] = [
  "....M......M....",
  "...MMM....MMM...",
  "..MMMMMMMMMMMM..",
  ".MMmmmmmmmmmmMM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFssesssseFmmM",
  "MmmFssssssssFmmM",
  "MmmFssnnnnssFmmM",
  "MmmFsswwwwssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  ".....ff..ff.....",
  "................",
];

const walk0: string[] = [
  "....M......M....",
  "...MMM....MMM...",
  "..MMMMMMMMMMMM..",
  ".MMmmmmmmmmmmMM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFsessssesFmmM",
  "MmmFssssssssFmmM",
  "MmmFssnnnnssFmmM",
  "MmmFsswwwwssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  "....fff..ff.....",
  "................",
];

const walk1: string[] = [
  "....M......M....",
  "...MMM....MMM...",
  "..MMMMMMMMMMMM..",
  ".MMmmmmmmmmmmMM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFsessssesFmmM",
  "MmmFssssssssFmmM",
  "MmmFssnnnnssFmmM",
  "MmmFsswwwwssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  ".....ff..fff....",
  "................",
];

const cheer0: string[] = [
  ".g..M......M..g.",
  "...MMM....MMM...",
  "g.MMMMMMMMMMMM.g",
  ".MMmmmmmmmmmmMM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFsessssesFmmM",
  "MmmFssssssssFmmM",
  "MmmFssnnnnssFmmM",
  "MmmFswwwwwwsFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".ff.ffffffff.ff.",
  ".....ff..ff.....",
  "................",
];

const sad0: string[] = [
  "....M......M....",
  "...MMM....MMM...",
  "..MMMMMMMMMMMM..",
  ".MMmmmmmmmmmmMM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFssssssssFmmM",
  "MmmFgsssssssFmmM",
  "MmmFssnnnnssFmmM",
  "MmmFssnnnnssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  ".....ff..ff.....",
  "................",
];

const sleep0: string[] = [
  "....M......M..g.",
  "...MMM....MMMg..",
  "..MMMMMMMMMMgM..",
  ".MMmmmmmmmmmmMM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFssssssssFmmM",
  "MmmFssssssssFmmM",
  "MmmFssnnnnssFmmM",
  "MmmFsswwwwssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  ".....ff..ff.....",
  "................",
];

export const SPRITES: Record<MascotState, string[][]> = {
  idle: [idle0, idle1, idle0, idle2], // blink + occasional sideglance loop
  walk: [walk0, walk1],
  cheer: [cheer0],
  sad: [sad0],
  sleep: [sleep0],
};

// Интервал смены кадра (мс). 0 = статика.
export const FRAME_INTERVAL_MS: Record<MascotState, number> = {
  idle: 1400,
  walk: 200,
  cheer: 220,
  sad: 0,
  sleep: 1500,
};
