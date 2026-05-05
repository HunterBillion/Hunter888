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
      // 2026-05-05 — `tab=activity` renamed to `tab=audit` because the
      // panel is the 152-ФЗ audit log, not the team's "activity" feed
      // (which lives on overview). Old bookmarks still land on the
      // canonical place in one hop.
      { source: "/admin/audit-log", destination: "/dashboard?tab=audit", permanent: true },
      { source: "/admin/users", destination: "/dashboard?tab=system", permanent: true },
      { source: "/admin/client-domain", destination: "/dashboard?tab=system", permanent: true },
      { source: "/admin/wiki", destination: "/dashboard?tab=content&sub=wiki", permanent: true },
      // 2026-04-26 — methodologist role retired, surfaces moved into the
      // dashboard tab. 2026-05-05 — the tab itself renamed
      // `methodology` → `content` so non-engineers stop reading "methodology"
      // as something they don't own. Each old standalone page maps to the
      // new canonical sub-tab in one hop.
      { source: "/methodologist", destination: "/dashboard?tab=content", permanent: true },
      { source: "/methodologist/sessions", destination: "/dashboard?tab=content&sub=sessions", permanent: true },
      { source: "/methodologist/arena-content", destination: "/dashboard?tab=content&sub=arena", permanent: true },
      { source: "/methodologist/scenarios", destination: "/dashboard?tab=content&sub=scenarios", permanent: true },
      // /methodologist/scoring deliberately drops to the tab root — the
      // scoring sub-tab itself was retired as a stale placeholder (2026-05-05).
      { source: "/methodologist/scoring", destination: "/dashboard?tab=content", permanent: true },
      // Stale `?tab=methodology` URLs (old emails, browser history,
      // WhatsApp links) are normalised by the dashboard page itself via
      // TAB_ALIASES — server-side query-only redirects via `has` would
      // loop on the same path, and middleware would be overkill for an
      // SPA rewrite. The address bar quietly switches to ?tab=content on
      // first render.
      // 2026-05-03 — /pvp/tutorial removed entirely (PR #204). Permanent
      // redirect to /pvp so any cached browser tab / bookmark / WhatsApp
      // link goes straight to the arena instead of showing a 404.
      { source: "/pvp/tutorial", destination: "/pvp", permanent: true },
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
