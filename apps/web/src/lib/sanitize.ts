/**
 * Text sanitization for chat / UI display.
 *
 * IMPORTANT architectural note (2026-04-20):
 * React's JSX `{variable}` interpolation already auto-escapes HTML for text
 * children. That means manually escaping via `sanitizeText()` BEFORE passing
 * a string into `{...}` produced DOUBLE escaping: quotes and ampersands in
 * legitimate content ended up rendered as literal `&quot;`, `&amp;`, etc.
 *
 * So `sanitizeText()` now does the opposite of what it used to do:
 * it DECODES any HTML entities that may have leaked in (from the LLM, from
 * legacy DB rows, from any upstream escape step) and returns clean Unicode.
 * React then auto-escapes on render, which is the correct boundary for XSS
 * protection. If you ever need the actual escape-for-innerHTML behavior,
 * use `escapeHtml()` below — it is only safe to feed into
 * `dangerouslySetInnerHTML`, never into plain JSX text children.
 */

// Common named HTML entities. Numeric (`&#39;`, `&#x27;`) are handled
// generically by the regex below, so only named ones need listing here.
const NAMED_ENTITIES: Record<string, string> = {
  amp: "&",
  quot: '"',
  apos: "'",
  lt: "<",
  gt: ">",
  nbsp: "\u00A0",
  mdash: "\u2014",
  ndash: "\u2013",
  laquo: "\u00AB",
  raquo: "\u00BB",
  hellip: "\u2026",
  copy: "\u00A9",
  reg: "\u00AE",
  trade: "\u2122",
};

/**
 * SSR-safe decoder: turns `&quot;`, `&amp;`, `&#39;`, `&#x27;`, etc. back into
 * real Unicode characters. Uses a single pass so `&amp;quot;` correctly stays
 * as `&quot;` (not double-decoded into `"`).
 */
function decodeHtmlEntities(input: string): string {
  return input.replace(
    /&(#x[0-9a-fA-F]+|#[0-9]+|[a-zA-Z][a-zA-Z0-9]{1,8});/g,
    (match, entity: string) => {
      // Numeric: &#123; or &#x7B;
      if (entity.charCodeAt(0) === 35 /* '#' */) {
        const isHex = entity[1] === "x" || entity[1] === "X";
        const codeStr = isHex ? entity.slice(2) : entity.slice(1);
        const code = parseInt(codeStr, isHex ? 16 : 10);
        if (Number.isFinite(code) && code > 0 && code <= 0x10ffff) {
          try {
            return String.fromCodePoint(code);
          } catch {
            return match;
          }
        }
        return match;
      }
      // Named: &amp;, &quot;, ...
      const val = NAMED_ENTITIES[entity];
      return val !== undefined ? val : match;
    },
  );
}

/**
 * Clean a string for display in the UI.
 *
 * - Returns `""` for null/undefined.
 * - Decodes any HTML entities that leaked in from upstream.
 * - Does NOT escape anything — React auto-escapes JSX text children.
 *
 * Only call this on strings that will be rendered as text children.
 * For strings passed to `dangerouslySetInnerHTML`, use `escapeHtml()`.
 */
export function sanitizeText(input: string | null | undefined): string {
  if (!input) return "";
  return decodeHtmlEntities(input);
}

/** Map used by `escapeHtml` — the INVERSE of decoding. */
const ESCAPE_MAP: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#x27;",
  "/": "&#x2F;",
};

/**
 * Escape text so it is safe to inject into HTML via `dangerouslySetInnerHTML`
 * or `innerHTML`. DO NOT use this for normal JSX text children — React
 * already escapes those, and pre-escaping will double-encode.
 */
export function escapeHtml(input: string | null | undefined): string {
  if (!input) return "";
  return input.replace(/[&<>"'/]/g, (char) => ESCAPE_MAP[char] || char);
}

/**
 * Strip HTML tags from input. Unchanged behavior.
 */
export function stripHtml(input: string | null | undefined): string {
  if (!input) return "";
  return input.replace(/<[^>]*>/g, "");
}

/**
 * Validate that a string doesn't contain script injection patterns.
 * Returns true if safe.
 */
export function isSafeInput(input: string): boolean {
  const dangerous = /<script|javascript:|on\w+\s*=/i;
  return !dangerous.test(input);
}

/**
 * Whitelist of allowed OAuth redirect domains.
 * Prevents open redirect attacks via compromised API responses.
 */
const ALLOWED_OAUTH_DOMAINS = new Set([
  "accounts.google.com",
  "oauth.yandex.ru",
  "oauth.yandex.com",
]);

/**
 * Validate an OAuth redirect URL — only allow known provider domains over HTTPS.
 * Returns the URL string if valid, or null if suspicious.
 */
export function validateOAuthUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") return null;
    if (!ALLOWED_OAUTH_DOMAINS.has(parsed.hostname)) return null;
    return url;
  } catch {
    return null;
  }
}
