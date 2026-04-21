// F2.5 - Middleware restrito de locale para rotas publicas SEO.
//
// Politica:
//   - App routes privadas (/, /chat/*, /conta, /favoritos, /plano, /auth/*),
//     /api/*, /_next/*, assets e /c/*/opengraph-image NUNCA passam por aqui
//     (ou passam e sao imediatamente bypass).
//   - Rotas publicas SEO (/ajuda, /privacy, /terms, /data-deletion, /c/[id],
//     /welcome) recebem o header de request `X-NEXT-INTL-LOCALE` para alimentar
//     `requestLocale` em frontend/i18n/request.ts.
//   - Prefixo de locale publico (/en, /es, /fr) faz REWRITE interno para o
//     path sem prefixo, mantendo o usuario na URL prefixada e o backend
//     servindo a rota canonica. Nada de redirect.
//   - Resolucao quando nao ha prefixo: cookie `wg_locale_choice` ->
//     header geo `X-Vercel-IP-Country` -> "pt-BR".
//   - Header geo `X-Vercel-IP-Country` e ecoado no response quando vier no
//     request, sem inventar valor.

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const SUPPORTED_LOCALES = ["pt-BR", "en-US", "es-419", "fr-FR"] as const;
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

const DEFAULT_LOCALE: SupportedLocale = "pt-BR";

const PUBLIC_PREFIX_TO_LOCALE: Record<string, SupportedLocale> = {
  en: "en-US",
  es: "es-419",
  fr: "fr-FR",
};

const LOCALE_BY_COUNTRY: Record<string, SupportedLocale> = {
  BR: "pt-BR",
  US: "en-US",
  MX: "es-419",
  FR: "fr-FR",
};

const PUBLIC_SEO_PATHS = new Set<string>([
  "/ajuda",
  "/privacy",
  "/terms",
  "/data-deletion",
  "/welcome",
]);

function isSupportedLocale(value: unknown): value is SupportedLocale {
  return (
    typeof value === "string" &&
    (SUPPORTED_LOCALES as readonly string[]).includes(value)
  );
}

// Caminhos que nunca devem ser tocados, mesmo que entrem no matcher por
// engano (ex: /en/chat/abc, /c/abc/opengraph-image).
function isBypassPath(pathname: string): boolean {
  if (pathname === "/") return true;
  if (pathname.startsWith("/api/")) return true;
  if (pathname.startsWith("/_next/")) return true;
  if (pathname.startsWith("/chat/") || pathname === "/chat") return true;
  if (pathname.startsWith("/auth/") || pathname === "/auth") return true;
  if (pathname === "/conta" || pathname.startsWith("/conta/")) return true;
  if (pathname === "/favoritos" || pathname.startsWith("/favoritos/")) return true;
  if (pathname === "/plano" || pathname.startsWith("/plano/")) return true;
  if (/\.(png|jpg|jpeg|svg|webp|ico|woff|woff2|css|js|map)$/i.test(pathname)) {
    return true;
  }
  if (/^\/c\/[^/]+\/opengraph-image/.test(pathname)) return true;
  return false;
}

function isPublicSeoPath(pathname: string): boolean {
  if (PUBLIC_SEO_PATHS.has(pathname)) return true;
  if (/^\/c\/[^/]+\/?$/.test(pathname)) return true;
  return false;
}

// Se pathname comeca com /en, /es, /fr -> retorna { locale, stripped }.
// Caso contrario -> { locale: null, stripped: pathname }.
function stripPublicLocalePrefix(pathname: string): {
  locale: SupportedLocale | null;
  stripped: string;
} {
  const match = pathname.match(/^\/(en|es|fr)(\/.*|$)/);
  if (!match) {
    return { locale: null, stripped: pathname };
  }
  const prefix = match[1];
  const remainder = match[2] || "/";
  return {
    locale: PUBLIC_PREFIX_TO_LOCALE[prefix] ?? null,
    stripped: remainder,
  };
}

function resolveLocaleFromRequest(request: NextRequest): SupportedLocale {
  const cookieChoice = request.cookies.get("wg_locale_choice")?.value;
  if (isSupportedLocale(cookieChoice)) {
    return cookieChoice;
  }

  const geoCountryRaw =
    request.headers.get("x-vercel-ip-country") ??
    request.headers.get("X-Vercel-IP-Country");
  const geoCountry = geoCountryRaw?.toUpperCase();
  if (geoCountry && geoCountry in LOCALE_BY_COUNTRY) {
    return LOCALE_BY_COUNTRY[geoCountry];
  }

  return DEFAULT_LOCALE;
}

function withLocaleHeader(
  request: NextRequest,
  locale: SupportedLocale,
): Headers {
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("X-NEXT-INTL-LOCALE", locale);
  return requestHeaders;
}

function copyGeoHeader(request: NextRequest, response: NextResponse): NextResponse {
  const geoCountry =
    request.headers.get("x-vercel-ip-country") ??
    request.headers.get("X-Vercel-IP-Country");
  if (geoCountry) {
    response.headers.set("X-Vercel-IP-Country", geoCountry);
  }
  return response;
}

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  if (isBypassPath(pathname)) {
    return NextResponse.next();
  }

  const { locale: prefixedLocale, stripped } = stripPublicLocalePrefix(pathname);

  // Apos stripar prefixo, se o caminho for bypass (ex: /en/chat/abc), nao toca.
  if (prefixedLocale && isBypassPath(stripped)) {
    return NextResponse.next();
  }

  // Apos stripar prefixo (ou se nao havia prefixo), so atuamos em rotas
  // publicas SEO. Qualquer outra coisa segue intocada.
  const targetPath = prefixedLocale ? stripped : pathname;
  if (!isPublicSeoPath(targetPath)) {
    return NextResponse.next();
  }

  const locale: SupportedLocale =
    prefixedLocale ?? resolveLocaleFromRequest(request);

  const requestHeaders = withLocaleHeader(request, locale);

  let response: NextResponse;
  if (prefixedLocale) {
    // Reescreve internamente para o path canonico sem prefixo.
    const rewriteUrl = request.nextUrl.clone();
    rewriteUrl.pathname = targetPath;
    response = NextResponse.rewrite(rewriteUrl, {
      request: { headers: requestHeaders },
    });
  } else {
    response = NextResponse.next({
      request: { headers: requestHeaders },
    });
  }

  return copyGeoHeader(request, response);
}

// F2.5b - Matcher allowlist explicito.
//
// Substitui os matchers amplos `/c/:path*`, `/en/:path*`, `/es/:path*`,
// `/fr/:path*` por entradas individuais por path/segmento. O middleware
// so e invocado para esta lista exata; tudo mais (OAuth, chat, conta,
// favoritos, plano, /api, /_next, assets, /c/<id>/opengraph-image) sequer
// entra no middleware.
//
// Os bypass defensivos em `isBypassPath` continuam ativos como cinto de
// seguranca (caso o matcher seja ampliado por engano em fase futura, o
// codigo segue ignorando paths privados).
export const config = {
  matcher: [
    // Sem prefixo
    "/ajuda",
    "/privacy",
    "/terms",
    "/data-deletion",
    "/welcome",
    "/c/:id",
    // Prefixo /en
    "/en/ajuda",
    "/en/privacy",
    "/en/terms",
    "/en/data-deletion",
    "/en/welcome",
    "/en/c/:id",
    // Prefixo /es
    "/es/ajuda",
    "/es/privacy",
    "/es/terms",
    "/es/data-deletion",
    "/es/welcome",
    "/es/c/:id",
    // Prefixo /fr
    "/fr/ajuda",
    "/fr/privacy",
    "/fr/terms",
    "/fr/data-deletion",
    "/fr/welcome",
    "/fr/c/:id",
  ],
};
