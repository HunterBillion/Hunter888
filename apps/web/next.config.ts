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

    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-XSS-Protection", value: "1; mode=block" },
          {
            key: "Permissions-Policy",
            value: "camera=(), geolocation=(), microphone=(self)",
          },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com",
              "style-src 'self' 'unsafe-inline'",
              // Allow loading user avatars from FastAPI static mount (cross-origin + LAN http)
              `img-src 'self' data: blob: https: http: ${apiOrigin}`,
              "font-src 'self' data:",
              // Scheme sources allow any host (needed when API URL is inferred from page hostname)
              `connect-src 'self' http: https: ws: wss: ${apiUrl} ${wsUrl}`,
              `media-src 'self' blob: https: http: ${apiOrigin}`,
              "worker-src 'self' blob:",
              "frame-ancestors 'none'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
