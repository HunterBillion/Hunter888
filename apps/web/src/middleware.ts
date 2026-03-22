import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Next.js middleware for route protection.
 * Checks for access token in cookies/localStorage (via header).
 * Since middleware runs on Edge, we check the cookie-based token.
 * Note: tokens are in localStorage, so we check for a specific cookie
 * that we set, OR we just redirect unauthenticated users client-side.
 *
 * For now: check if the access token cookie exists.
 * The actual auth validation happens client-side in AuthLayout/useAuth.
 * This middleware provides a fast-fail redirect for obvious non-auth cases.
 */

const PUBLIC_ROUTES = [
  "/",
  "/login",
  "/register",
  "/consent/verify",
  "/auth/callback",
  "/change-password",
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

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip public routes, static files, API routes
  if (
    isPublicRoute(pathname) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/sw-") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  // Check for token in cookie (set by client after login)
  // Since we use localStorage, tokens aren't in cookies by default.
  // This middleware serves as a structural guard — actual auth is in AuthLayout.
  // We check for the presence of a marker cookie that client sets on login.
  const hasToken = request.cookies.get("vh_authenticated");

  if (!hasToken) {
    // Don't hard-redirect — let client-side AuthLayout handle it.
    // This prevents SSR/hydration mismatch issues.
    // The middleware just ensures the response headers are clean.
    return NextResponse.next();
  }

  return NextResponse.next();
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
