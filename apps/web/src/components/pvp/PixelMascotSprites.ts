/**
 * PixelMascotSprites — 16×16 chunky-pixel маскот-лев для PvP лобби.
 *
 * v4 (2026-05-07): redesigned for stronger lion silhouette —
 *   - 2 distinct triangular ears with golden inner-ear pixels
 *   - full circular mane wreath wrapping head top + chin
 *   - face has 1-px eyes flanked by 1-px white sparkle (more readable
 *     at small sizes than 2-wide eye blocks)
 *   - smile with dark lip-corner pixels framing teeth
 *   - paws sit on a ground line (2-px M markers under each paw)
 * Sprites generated via /tmp gen-script and validated 16×16 each.
 *
 * Стиль и формат идентичны PixelAvatarSprites.ts / PixelIcon.tsx:
 *   - сетка 16 строк × 16 символов
 *   - один char = 1 ячейка SVG `<rect width=1 height=1>`
 *   - `image-rendering: pixelated`
 *
 * Литералы (закрытый алфавит):
 *   .  transparent
 *   M  mane (тёмный коричневый)
 *   m  mane (средний коричневый)
 *   F  face fur (золотой яркий)
 *   f  body fur (золотой средний)
 *   s  skin / muzzle (светлый кремовый)
 *   e  eye (чёрный)
 *   n  nose (тёмно-коричневый)
 *   w  tooth / mouth glint / eye sparkle (белый)
 *   g  accent — заменяется на проп `accent` (sparkle / Z / tear / wave)
 */

export type MascotState = "idle" | "walk" | "cheer" | "sad" | "sleep" | "wave";

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
  "...MM......MM...",
  "...MFMMMMMMFM...",
  "..MmmmmmmmmmmM..",
  ".MmmmmmmmmmmmmM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFsessssesFmmM",
  "MmmFssssssssFmmM",
  "MmmFsssnnsssFmmM",
  "MmmFsssswsssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  "....fff..fff....",
  ".....MM..MM.....",
];

const idle1: string[] = [
  "...MM......MM...",
  "...MFMMMMMMFM...",
  "..MmmmmmmmmmmM..",
  ".MmmmmmmmmmmmmM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFssssssssFmmM",
  "MmmFssssssssFmmM",
  "MmmFsssnnsssFmmM",
  "MmmFsssswsssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  "....fff..fff....",
  ".....MM..MM.....",
];

const walk0: string[] = [
  "...MM......MM...",
  "...MFMMMMMMFM...",
  "..MmmmmmmmmmmM..",
  ".MmmmmmmmmmmmmM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFsessssesFmmM",
  "MmmFssssssssFmmM",
  "MmmFsssnnsssFmmM",
  "MmmFsssswsssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  "...fff...fff....",
  "....MM...MM.....",
];

const walk1: string[] = [
  "...MM......MM...",
  "...MFMMMMMMFM...",
  "..MmmmmmmmmmmM..",
  ".MmmmmmmmmmmmmM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFsessssesFmmM",
  "MmmFssssssssFmmM",
  "MmmFsssnnsssFmmM",
  "MmmFsssswsssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  "....fff...fff...",
  ".....MM...MM....",
];

const cheer0: string[] = [
  "g..MM......MM..g",
  "...MFMMMMMMFM...",
  ".gMmmmmmmmmmmMg.",
  ".MmmmmmmmmmmmmM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFsessssesFmmM",
  "MmmFssssssssFmmM",
  "MmmFsssnnsssFmmM",
  "MmmFsssswsssFmmM",
  ".MmmFFFFFFFFmmM.",
  "f.MmmmmmmmmmmM.f",
  "f...MMMMMMMM...f",
  ".f...ffffff...f.",
  "....fff..fff....",
  ".....MM..MM.....",
];

const sad0: string[] = [
  "................",
  "...MM......MM...",
  "...MFMMMMMMFM...",
  "..MmmmmmmmmmmM..",
  ".MmmmmmmmmmmmmM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFgsssssssFmmM",
  "MmmFsssnnsssFmmM",
  "MmmFssnnnnssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  "....fff..fff....",
  "................",
];

const sleep0: string[] = [
  "...MM......MMgg.",
  "...MFMMMMMMFg...",
  "..MmmmmmmmmgmM..",
  ".MmmmmmmmmmmmmM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFssssssssFmmM",
  "MmmFssssssssFmmM",
  "MmmFsssnnsssFmmM",
  "MmmFsssswsssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmM..",
  "....MMMMMMMM....",
  ".....ffffff.....",
  "....fff..fff....",
  ".....MM..MM.....",
];

// v4 NEW state — friendly hello wave (used on lobby first-load greeting).
const wave0: string[] = [
  "...MM......MM...",
  "...MFMMMMMMFM...",
  "..MmmmmmmmmmmM..",
  ".MmmmmmmmmmmmmM.",
  "MmmFFFFFFFFFFmmM",
  "MmmFssssssssFmmM",
  "MmmFsessssesFmmM",
  "MmmFssssssssFmmM",
  "MmmFsssnnsssFmmM",
  "MmmFsssswsssFmmM",
  ".MmmFFFFFFFFmmM.",
  "..MmmmmmmmmmmMfg",
  "....MMMMMMMM..ff",
  ".....ffffff....f",
  "....fff...ff....",
  ".....MM...M.....",
];

export const SPRITES: Record<MascotState, string[][]> = {
  idle: [idle0, idle1, idle0, idle0], // open-blink-open-open (slow blink)
  walk: [walk0, walk1],
  cheer: [cheer0],
  sad: [sad0],
  sleep: [sleep0],
  wave: [wave0],
};

export const FRAME_INTERVAL_MS: Record<MascotState, number> = {
  idle: 1200,
  walk: 200,
  cheer: 220,
  sad: 0,
  sleep: 1500,
  wave: 0,
};
