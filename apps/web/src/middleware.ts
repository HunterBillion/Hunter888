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

/** API origin for CSP — avatars & video assets load from API host. */
function apiOriginForCsp(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    return new URL(raw).origin;
  } catch {
    return "http://localhost:8000";
  }
}

/** Build the full CSP header value for a given nonce. */
function buildCsp(nonce: string): string {
  const apiOrigin = apiOriginForCsp();
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const wsUrl = (process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000").replace(/^ws/, "ws");
  const isDev = process.env.NODE_ENV !== "production";

  // Development: unsafe-eval is required for Next.js Fast Refresh / HMR.
  // Production: strict nonce — no unsafe-inline, no unsafe-eval.
  const scriptSrc = isDev
    ? `script-src 'self' 'unsafe-inline' 'unsafe-eval'`
    : `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`;

  // Tailwind injects styles at runtime — unsafe-inline is required.
  const styleSrc = "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com";

  return [
    "default-src 'self'",
    scriptSrc,
    styleSrc,
    `img-src 'self' data: blob: ${apiOrigin} https://cdn.jsdelivr.net`,
    "font-src 'self' data: https://fonts.gstatic.com",
    `connect-src 'self' ${apiUrl} ${wsUrl} https://met4citizen.github.io`,
    `media-src 'self' blob: ${apiOrigin}`,
    "worker-src 'self' blob:",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
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
  "/test",
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
  "/admin": ["admin"],
  "/methodologist": ["admin", "methodologist"],
  "/dashboard": ["admin", "rop"],
  "/reports": ["admin", "rop", "manager", "methodologist"],
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
  const cspHeaderValue = buildCsp(nonce);

  // ── 2. Skip auth guard for public/static routes ──────────────────────
  if (
    isPublicRoute(pathname) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/sw-") ||
    pathname.includes(".")
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
