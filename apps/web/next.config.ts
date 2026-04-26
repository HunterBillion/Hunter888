import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Security: disable source maps in production
  productionBrowserSourceMaps: false,
  // Hide dev overlay indicators (build error button)
  devIndicators: false,

  // 2026-04-26 — /admin route deleted, all surfaces moved into /dashboard.
  // These permanent redirects keep existing bookmarks and the few legacy
  // links inside the app working without 404s. Remove after a release or
  // two once analytics confirm no traffic.
  async redirects() {
    return [
      { source: "/admin", destination: "/dashboard?tab=system", permanent: true },
      { source: "/admin/audit-log", destination: "/dashboard?tab=activity", permanent: true },
      { source: "/admin/users", destination: "/dashboard?tab=system", permanent: true },
      { source: "/admin/client-domain", destination: "/dashboard?tab=system", permanent: true },
      { source: "/admin/wiki", destination: "/dashboard?tab=methodology", permanent: true },
      // 2026-04-26 — methodologist role retired, surfaces moved into the
      // dashboard Methodology tab. Permanent redirects keep existing
      // bookmarks and any pilot scripts working without 404s. Each old
      // standalone page maps to its new sub-tab via ?sub=...
      { source: "/methodologist", destination: "/dashboard?tab=methodology", permanent: true },
      { source: "/methodologist/sessions", destination: "/dashboard?tab=methodology&sub=sessions", permanent: true },
      { source: "/methodologist/arena-content", destination: "/dashboard?tab=methodology&sub=arena", permanent: true },
      { source: "/methodologist/scenarios", destination: "/dashboard?tab=methodology&sub=scenarios", permanent: true },
      { source: "/methodologist/scoring", destination: "/dashboard?tab=methodology&sub=scoring", permanent: true },
    ];
  },

  // Security headers (non-CSP).
  // Content-Security-Policy is set by middleware.ts with a per-request nonce.
  async headers() {
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
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
          {
            key: "X-DNS-Prefetch-Control",
            value: "on",
          },
          {
            key: "Cross-Origin-Opener-Policy",
            value: "same-origin",
          },
          {
            key: "Cross-Origin-Resource-Policy",
            value: "same-origin",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
