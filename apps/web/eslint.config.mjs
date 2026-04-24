// ESLint 9 flat config — replaces the `next lint` interactive wizard that
// blocked CI. Minimal rules: use the Next.js core-web-vitals preset,
// ignore build artefacts, and leave fine-grained tuning for later.
import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({
  baseDirectory: import.meta.dirname,
});

export default [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [
      ".next/**",
      "out/**",
      "build/**",
      "node_modules/**",
      "public/**",
      "src/types/api.ts", // auto-generated openapi output — do not lint
    ],
  },
  {
    // Existing codebase has accumulated patterns that the strict Next.js
    // preset flags as errors but that are well-understood in context
    // (explicit `any` in test doubles, unused eslint-disable comments,
    // React hook deps). Degrade those to warnings so PRs don't wedge on
    // pre-existing code. Fix them opportunistically in dedicated PRs.
    rules: {
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-vars": "warn",
      "@typescript-eslint/no-unused-expressions": "warn",
      "@typescript-eslint/ban-ts-comment": "warn",
      "@typescript-eslint/no-require-imports": "warn",
      "@typescript-eslint/no-unsafe-function-type": "warn",
      "react-hooks/exhaustive-deps": "warn",
      "react/no-unescaped-entities": "warn",
      "react/jsx-no-comment-textnodes": "warn",
      "@next/next/no-img-element": "warn",
      "@next/next/no-html-link-for-pages": "warn",
      "prefer-const": "warn",
    },
  },
];
