import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Next.js middleware — route protection + nonce-based Content-Security-Policy.
 *
 * 1. Generates a cryptographic nonce per request.
 * 2. Sets the CSP header with `'nonce-<value>'` for script-src (production)
 *    or `'unsafe-eval'` for script-src (development — required for HMR).
 * 3. Passes the nonce to the App Router via the `x-nonce` response header
 *    so layout.tsx can embed it in a <meta> tag for client scripts.
 * 4. Performs the same auth-guard redirect logic as before.
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** API origin for CSP — avatars & video assets load from API host.
 *  When env is default localhost but request comes from LAN IP,
 *  infer API origin from request host (same logic as public-origin.ts).
 */
function apiOriginForCsp(requestHost?: string | null): string {
  const raw = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    const parsed = new URL(raw);
    if (
      requestHost &&
      (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1")
    ) {
      const reqHostname = requestHost.split(":")[0];
      if (reqHostname && reqHostname !== "localhost" && reqHostname !== "127.0.0.1") {
        const proto = parsed.protocol;  // http: or https:
        return `${proto}//${reqHostname}:8000`;
      }
    }
    return parsed.origin;
  } catch {
    return "http://localhost:8000";
  }
}

/** Build the full CSP header value for a given nonce. */
function buildCsp(nonce: string, requestHost?: string | null): string {
  const apiOrigin = apiOriginForCsp(requestHost);
  const apiUrl = apiOrigin;
  // Derive WS URL from API origin
  const wsProto = apiOrigin.startsWith("https") ? "wss:" : "ws:";
  const apiHost = apiOrigin.replace(/^https?:\/\//, "");
  const wsUrl = `${wsProto}//${apiHost}`;
  const isDev = process.env.NODE_ENV !== "production";

  // Development: unsafe-eval is required for Next.js Fast Refresh / HMR.
  // Production: strict nonce — no unsafe-inline, no unsafe-eval.
  // next-themes injects an inline script to prevent FOUC (flash of wrong theme).
  // Its hash must be whitelisted alongside the nonce for other scripts.
  const nextThemesHash = "'sha256-osMMQj3FsFuFoINhDY6u/ERO7gP52tI8DTruJmDXHD8='";
  const scriptSrc = isDev
    ? `script-src 'self' 'unsafe-inline' 'unsafe-eval'`
    : `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${nextThemesHash}`;

  // Tailwind injects styles at runtime — unsafe-inline is required.
  const styleSrc = "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com";

  return [
    "default-src 'self'",
    scriptSrc,
    styleSrc,
    `img-src 'self' data: blob: ${apiOrigin} https://cdn.jsdelivr.net https://*.ytimg.com https://*.vimeocdn.com`,
    "font-src 'self' data: https://fonts.gstatic.com",
    `connect-src 'self' ${apiUrl} ${wsUrl} https://met4citizen.github.io https://accounts.google.com`,
    `media-src 'self' blob: ${apiOrigin} https://*.googlevideo.com`,
    // Embedded video players — YouTube + Vimeo iframes allowed.
    // Expand here if you add other providers (Rutube, VK Video, etc.).
    "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com https://player.vimeo.com https://accounts.google.com https://oauth.yandex.ru",
    "worker-src 'self' blob:",
    // frame-ancestors 'none' — nothing may iframe x-hunter.expert (anti-clickjacking).
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self' https://accounts.google.com https://oauth.yandex.ru",
  ].join("; ");
}

// ---------------------------------------------------------------------------
// Route protection
// ---------------------------------------------------------------------------

const PUBLIC_ROUTES = [
  "/",
  "/product",
  "/pricing",
  "/login",
  "/register",
  "/consent/verify",
  "/auth/callback",
  "/change-password",
  "/reset-password",
  // S1-03: /test removed from PUBLIC_ROUTES — requires admin role
];

function isPublicRoute(pathname: string): boolean {
  return PUBLIC_ROUTES.some((route) => {
    if (route === pathname) return true;
    if (route.endsWith("/") && pathname.startsWith(route)) return true;
    // Allow consent/verify/* paths
    if (route === "/consent/verify" && pathname.startsWith("/consent/verify")) return true;
    return false;
  });
}

// ---------------------------------------------------------------------------
// Role-based access control
// ---------------------------------------------------------------------------

type UserRole = "manager" | "rop" | "methodologist" | "admin";

/**
 * Map of protected route prefixes → allowed roles.
 * Any authenticated user NOT in the allowed list gets redirected to /home.
 */
const ROLE_PROTECTED_ROUTES: Record<string, UserRole[]> = {
  // /admin removed 2026-04-26 — все админские поверхности живут в
  // /dashboard как табы. Старые пути редиректятся в next.config.ts.
  "/test": ["admin"],  // S1-03: QA test page — admin only
  "/methodologist": ["admin", "methodologist"],
  "/dashboard": ["admin", "rop"],
  // "/reports" removed — consolidated into /dashboard?tab=reports
  "/wiki": ["admin", "rop", "manager"],
  "/clients": ["admin", "rop", "manager", "methodologist"],
};

/**
 * Extract user role from JWT access_token without verifying signature.
 *
 * This is safe in middleware because:
 * 1. The token was issued by our backend and is verified on every API call
 * 2. Middleware role check is a UX guard (prevents loading unauthorized pages)
 * 3. The real authorization happens server-side on data access
 *
 * If the token is malformed or missing role, returns null → access denied.
 */
function extractRoleFromJwt(token: string): UserRole | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    // Decode the payload (base64url → JSON)
    const payload = JSON.parse(
      Buffer.from(parts[1].replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf-8")
    );
    const role = payload.role || payload.user_role || payload.sub_role;
    if (role && ["manager", "rop", "methodologist", "admin"].includes(role)) {
      return role as UserRole;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Check if a pathname requires a specific role and whether the user has it.
 * Returns redirect URL if unauthorized, null if allowed.
 */
function checkRoleAccess(pathname: string, token: string | undefined): string | null {
  if (!token) return null; // No token = auth guard will handle redirect to /login

  for (const [routePrefix, allowedRoles] of Object.entries(ROLE_PROTECTED_ROUTES)) {
    if (pathname.startsWith(routePrefix)) {
      const role = extractRoleFromJwt(token);
      if (!role || !allowedRoles.includes(role)) {
        return "/home"; // Redirect unauthorized users to home
      }
      break;
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Middleware entry point
// ---------------------------------------------------------------------------

export function middleware(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;

  // ── 1. Generate nonce ────────────────────────────────────────────────
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const cspHeaderValue = buildCsp(nonce, request.headers.get("host"));

  // ── 2. Skip auth guard for public/static routes ──────────────────────
  if (
    isPublicRoute(pathname) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/sw-") ||
    /\.(js|css|ico|png|jpg|jpeg|gif|svg|webp|woff2?|ttf|eot|map|json|txt|xml|webmanifest)$/i.test(pathname)
  ) {
    const response = NextResponse.next();
    response.headers.set("Content-Security-Policy", cspHeaderValue);
    response.headers.set("x-nonce", nonce);
    return response;
  }

  // ── 3. Auth guard ────────────────────────────────────────────────────
  const hasAccessToken = request.cookies.get("access_token");
  const hasMarker = request.cookies.get("vh_authenticated");

  if (!hasAccessToken && !hasMarker) {
    // GUARD: Prevent infinite redirect loops.
    const redirectTarget = searchParams.get("redirect");
    if (redirectTarget === "/login" || pathname === "/login") {
      const response = NextResponse.next();
      response.headers.set("Content-Security-Policy", cspHeaderValue);
      response.headers.set("x-nonce", nonce);
      return response;
    }

    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    const response = NextResponse.redirect(loginUrl);

    // Clear potentially stale/invalid auth cookies
    response.cookies.delete("access_token");
    response.cookies.delete("vh_authenticated");

    response.headers.set("Content-Security-Policy", cspHeaderValue);
    response.headers.set("x-nonce", nonce);
    return response;
  }

  // ── 4. Role-based access control ──────────────────────────────────────
  const tokenValue = hasAccessToken?.value;
  const roleRedirect = checkRoleAccess(pathname, tokenValue);
  if (roleRedirect) {
    const redirectUrl = new URL(roleRedirect, request.url);
    const response = NextResponse.redirect(redirectUrl);
    response.headers.set("Content-Security-Policy", cspHeaderValue);
    response.headers.set("x-nonce", nonce);
    return response;
  }

  // ── 5. Authenticated + authorized request — pass through ────────────
  const response = NextResponse.next();
  response.headers.set("Content-Security-Policy", cspHeaderValue);
  response.headers.set("x-nonce", nonce);
  return response;
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - _next (static files)
     * - api routes
     * - static files with extensions
     */
    "/((?!_next/static|_next/image|favicon.ico|manifest.json|icon-|sw-).*)",
  ],
};
