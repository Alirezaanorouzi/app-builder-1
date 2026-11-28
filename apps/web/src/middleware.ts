import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const SESSION_COOKIE = "ab_session";
const AUTH_PATHS = new Set(["/login", "/register"]);

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api/auth") ||
    pathname === "/auth-galaxy.jpg" ||
    pathname.startsWith("/fonts/")
  ) {
    return NextResponse.next();
  }

  const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);
  const isAuthPath = AUTH_PATHS.has(pathname);

  if (hasSession && isAuthPath) {
    return NextResponse.redirect(new URL("/", req.url));
  }

  if (!hasSession && !isAuthPath && !pathname.startsWith("/api/")) {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};