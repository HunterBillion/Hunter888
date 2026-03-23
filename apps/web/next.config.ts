import type { NextConfig } from "next";

/** API origin for CSP — avatars & video avatars load from API host (not same-origin as Next). */
function apiOriginForCsp(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    return new URL(raw).origin;
  } catch {
    return "http://localhost:8000";
  }
}

const nextConfig: NextConfig = {
  output: "standalone",
  // Security: disable source maps in production
  productionBrowserSourceMaps: false,

  // Security headers
  async headers() {
    const apiOrigin = apiOriginForCsp();
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const wsUrl = (process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000").replace(/^ws/, "ws");
    const isDev = process.env.NODE_ENV !== "production";

    // In development: allow unsafe-inline/eval for hot-reload & devtools.
    // In production: strict CSP with no inline scripts/styles.
    // NOTE: Next.js handles script nonces automatically when CSP header
    // contains 'strict-dynamic' (https://nextjs.org/docs/app/building-your-application/configuring/content-security-policy).
    const scriptSrc = isDev
      ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
      : "script-src 'self' 'strict-dynamic' https:";

    const styleSrc = isDev
      ? "style-src 'self' 'unsafe-inline'"
      : "style-src 'self' 'unsafe-inline'";
    // NOTE: style-src still needs unsafe-inline because Tailwind/CSS-in-JS
    // inject styles at runtime. Styles can't execute code, so XSS risk is minimal.

    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-XSS-Protection", value: "0" }, // Disabled — modern CSP makes it redundant; old versions can cause issues
          {
            key: "Permissions-Policy",
            value: "camera=(), geolocation=(), microphone=(self)",
          },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              scriptSrc,
              styleSrc,
              // Allow loading user avatars from FastAPI static mount (cross-origin + LAN http)
              `img-src 'self' data: blob: https: http: ${apiOrigin}`,
              "font-src 'self' data:",
              // Scheme sources allow any host (needed when API URL is inferred from page hostname)
              `connect-src 'self' http: https: ws: wss: ${apiUrl} ${wsUrl}`,
              `media-src 'self' blob: https: http: ${apiOrigin}`,
              "worker-src 'self' blob:",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
