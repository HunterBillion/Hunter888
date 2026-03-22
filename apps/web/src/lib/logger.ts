/**
 * Production-safe logger.
 * Only logs in development. Silenced in production builds.
 * Prevents sensitive data from appearing in browser console.
 */

const isDev = process.env.NODE_ENV === "development";

export const logger = {
  log: (...args: unknown[]) => {
    if (isDev) console.log(...args);
  },
  warn: (...args: unknown[]) => {
    if (isDev) console.warn(...args);
  },
  error: (...args: unknown[]) => {
    // Errors always logged (needed for debugging)
    // but strip sensitive data in production
    if (isDev) {
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
