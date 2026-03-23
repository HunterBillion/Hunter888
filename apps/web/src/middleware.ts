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
  const { pathname, searchParams } = request.nextUrl;

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

  // Check for httpOnly access_token cookie OR marker cookie
  const hasAccessToken = request.cookies.get("access_token");
  const hasMarker = request.cookies.get("vh_authenticated");

  if (!hasAccessToken && !hasMarker) {
    // GUARD: Prevent infinite redirect loops.
    // If the client was ALREADY redirected once (indicated by ?redirect= param
    // pointing at /login), don't redirect again — break the loop.
    const redirectTarget = searchParams.get("redirect");
    if (redirectTarget === "/login" || pathname === "/login") {
      return NextResponse.next();
    }

    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    const response = NextResponse.redirect(loginUrl);

    // Clear potentially stale/invalid auth cookies that might cause loops
    // (e.g., expired access_token still present as a cookie)
    response.cookies.delete("access_token");
    response.cookies.delete("vh_authenticated");

    return response;
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
