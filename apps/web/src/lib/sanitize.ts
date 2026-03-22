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
export function sanitizeText(input: string): string {
  return input.replace(/[&<>"'/]/g, (char) => HTML_ENTITIES[char] || char);
}

/**
 * Strip HTML tags from input.
 * More aggressive than sanitizeText — removes tags entirely.
 */
export function stripHtml(input: string): string {
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
