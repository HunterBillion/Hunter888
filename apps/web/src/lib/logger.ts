/**
 * Production-safe logger.
 * Only logs in development. Silenced in production builds.
 * Prevents sensitive data from appearing in browser console.
 *
 * `isDev` is computed lazily per-call so test harnesses (vitest's
 * `vi.stubEnv("NODE_ENV", ...)`) can flip mode at runtime. The previous
 * version captured `process.env.NODE_ENV` at module-load time, which
 * happens once before the test body runs — every dev/prod-distinguishing
 * test silently failed because `isDev` was frozen as `false` (vitest
 * defaults `NODE_ENV` to `"test"`).
 */

const isDev = (): boolean => process.env.NODE_ENV === "development";

export const logger = {
  log: (...args: unknown[]) => {
    if (isDev()) console.log(...args);
  },
  warn: (...args: unknown[]) => {
    if (isDev()) console.warn(...args);
  },
  error: (...args: unknown[]) => {
    // Errors always logged (needed for debugging)
    // but strip sensitive data in production
    if (isDev()) {
      console.error(...args);
    } else {
      // In production: log only error message, not full objects
      const msg = args.map((a) =>
        a instanceof Error ? a.message : typeof a === "string" ? a : "[redacted]"
      );
      console.error(...msg);
    }
  },
};
