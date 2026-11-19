import { NextResponse, type NextRequest } from "next/server";

import { defaultLocale, isLocale } from "@/lib/i18n";

// «/» и пути без языка → /{kk|ru}/… (по cookie, иначе по Accept-Language, иначе ru).
// Демо для ментора: если задан DEMO_PASSWORD, весь сайт и прокси API закрыты паролем (HTTP Basic, логин любой).
function demoAuthorized(request: NextRequest): boolean {
  const password = process.env.DEMO_PASSWORD;
  if (!password) return true;
  const header = request.headers.get("authorization") ?? "";
  if (!header.startsWith("Basic ")) return false;
  try {
    const decoded = atob(header.slice(6));
    return decoded.slice(decoded.indexOf(":") + 1) === password;
  } catch {
    return false;
  }
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (!demoAuthorized(request)) {
    return new NextResponse("Демо ЖКХ AI ЮРИСТ: нужен пароль", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="ZhKH AI demo", charset="UTF-8"' },
    });
  }
  if (pathname.startsWith("/backend/")) return NextResponse.next();
  const first = pathname.split("/")[1] ?? "";
  if (isLocale(first)) return NextResponse.next();

  const cookie = request.cookies.get("locale")?.value;
  const accept = request.headers.get("accept-language") ?? "";
  const locale = cookie && isLocale(cookie) ? cookie : /\bkk\b|\bkz\b/i.test(accept) ? "kk" : defaultLocale;

  const url = request.nextUrl.clone();
  url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(url);
}

export const config = {
  // /backend — прокси API (в путях бывают точки, напр. .docx), его закрываем паролем тоже
  matcher: ["/backend/:path*", "/((?!_next|api|favicon.ico|.*\\..*).*)"],
};
