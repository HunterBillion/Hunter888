/**
 * Input sanitization for XSS prevention.
 * All user-generated content (chat messages, profile names, etc.)
 * should pass through sanitizeText before display.
 */

const HTML_ENTITIES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#x27;",
  "/": "&#x2F;",
};

/**
 * Escape HTML entities in user input.
 * Prevents XSS when rendering user content.
 */
export function sanitizeText(input: string | null | undefined): string {
  if (!input) return "";
  return input.replace(/[&<>"'/]/g, (char) => HTML_ENTITIES[char] || char);
}

/**
 * Strip HTML tags from input.
 * More aggressive than sanitizeText — removes tags entirely.
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
