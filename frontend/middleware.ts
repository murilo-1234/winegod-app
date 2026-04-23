// F2.5 + F7.6 - Middleware de locale publico SEO + age gate por mercado.
//
// Politica F2.5 (mantida):
//   - Rotas publicas SEO (/ajuda, /privacy, /terms, /data-deletion, /c/[id],
//     /welcome) recebem o header de request `X-NEXT-INTL-LOCALE` para
//     alimentar `requestLocale` em frontend/i18n/request.ts.
//   - Prefixo de locale publico (/en, /es, /fr) faz REWRITE interno para o
//     path sem prefixo, mantendo o usuario na URL prefixada.
//   - Resolucao quando nao ha prefixo: cookie `wg_locale_choice` ->
//     header geo `X-Vercel-IP-Country` -> "pt-BR".
//
// Politica F7.6 (novo):
//   - Caminhos privados/principais (`/`, `/chat/*`, `/conta`, `/favoritos`,
//     `/plano`, `/ajuda`) ficam protegidos por age gate.
//   - Se o cookie `wg_age_verified` nao existir ou estiver em formato
//     invalido, redireciona para `/age-verify?next=<pathname_original>`.
//   - `/age-verify` e rotas publicas de leitura (/legal/*, share /c/*,
//     assets, /_next/*, /api/*) nao passam pelo gate.
//   - O gate respeita prefixo de locale: `/en/chat/abc` checa o cookie e
//     redireciona para `/age-verify?next=/en/chat/abc`.

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const SUPPORTED_LOCALES = ["pt-BR", "en-US", "es-419", "fr-FR"] as const;
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

const DEFAULT_LOCALE: SupportedLocale = "pt-BR";

// F9.9 (support fix) - resolucao de enabled_locales estatica via env.
// O kill switch principal (Plano A, F0.6) continua sendo a tabela
// feature_flags no backend, lida dinamicamente pelas rotas `/api/config/*`.
// Este middleware NAO chama backend; precisa saber em tempo de edge quais
// locales publicos sao indexaveis para decidir 301 vs rewrite em share
// links. A fonte de verdade estatica aqui e a env var
// NEXT_PUBLIC_ENABLED_LOCALES (com fallback NEXT_PUBLIC_ENABLED_LOCALES_FALLBACK
// = ENABLED_LOCALES). Quando nenhuma estiver definida, assume os 4
// supported locales (comportamento pre-F9.9, sem regressao). Lista e
// CSV ou JSON array.
function resolveStaticallyEnabledLocales(): readonly SupportedLocale[] {
  const raw =
    process.env.NEXT_PUBLIC_ENABLED_LOCALES ??
    process.env.ENABLED_LOCALES ??
    "";
  if (!raw) {
    return SUPPORTED_LOCALES;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    parsed = raw.split(",").map((s) => s.trim()).filter(Boolean);
  }
  if (!Array.isArray(parsed)) return SUPPORTED_LOCALES;
  const filtered = parsed.filter(isSupportedLocale);
  if (filtered.length === 0) return SUPPORTED_LOCALES;
  return filtered;
}

const STATICALLY_ENABLED_LOCALES: readonly SupportedLocale[] =
  resolveStaticallyEnabledLocales();

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

const AGE_VERIFIED_COOKIE = "wg_age_verified";

function isSupportedLocale(value: unknown): value is SupportedLocale {
  return (
    typeof value === "string" &&
    (SUPPORTED_LOCALES as readonly string[]).includes(value)
  );
}

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

// F7.6 - Paths que exigem age gate (apos strip de prefixo de locale).
// /age-verify, /legal/*, /privacy, /terms, /data-deletion, /c/*, /api/*,
// /_next/*, /auth/* e assets NAO entram aqui (publicos ou por bypass).
function requiresAgeGate(pathname: string): boolean {
  if (pathname === "/") return true;
  if (pathname === "/chat" || pathname.startsWith("/chat/")) return true;
  if (pathname === "/conta" || pathname.startsWith("/conta/")) return true;
  if (pathname === "/favoritos" || pathname.startsWith("/favoritos/")) return true;
  if (pathname === "/plano" || pathname.startsWith("/plano/")) return true;
  if (pathname === "/ajuda" || pathname.startsWith("/ajuda/")) return true;
  return false;
}

// F7.6 - Validacao minima do cookie wg_age_verified.
// Formato: "<MARKET>:<MIN_AGE>:<ISO_TIMESTAMP>" (gravado em AgeGate.tsx).
// Aceita qualquer market alfabetico 2-8 chars + inteiro + ISO parseavel.
// Nao compara country/age atuais vs cookie — se o cookie existe e parseia,
// esta verificado. Expiracao e responsabilidade do cookie TTL (1 ano).
function isAgeVerified(request: NextRequest): boolean {
  const raw = request.cookies.get(AGE_VERIFIED_COOKIE)?.value;
  if (!raw) return false;
  let decoded: string;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return false;
  }
  const parts = decoded.split(":");
  if (parts.length < 3) return false;
  const country = parts[0];
  const ageStr = parts[1];
  const ts = parts.slice(2).join(":"); // ISO timestamps contem ':'
  if (!/^[A-Za-z]{2,10}$/.test(country)) return false;
  if (!/^\d+$/.test(ageStr)) return false;
  if (Number.isNaN(Date.parse(ts))) return false;
  return true;
}

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

  // F7.6 - Age gate check ANTES de qualquer outra coisa.
  // Respeita prefixo de locale: /en/chat/abc -> stripped=/chat/abc.
  const { locale: prefixedLocale, stripped } = stripPublicLocalePrefix(pathname);
  const effectivePath = prefixedLocale ? stripped : pathname;

  if (requiresAgeGate(effectivePath) && !isAgeVerified(request)) {
    const redirectUrl = request.nextUrl.clone();
    // H4 F1.4: preservar o prefixo de locale na URL do age gate para que
    // a primeira visita de /en|/es|/fr/<rota> chegue num age gate no mesmo
    // idioma, sem cair em pt-BR como default do request config.
    const localePrefix = prefixedLocale === "en-US"
      ? "/en"
      : prefixedLocale === "es-419"
        ? "/es"
        : prefixedLocale === "fr-FR"
          ? "/fr"
          : "";
    redirectUrl.pathname = `${localePrefix}/age-verify`;
    redirectUrl.search = "";
    redirectUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(redirectUrl, 302);
  }

  // H4 F1.4: rewrite de /{en,es,fr}/age-verify para /age-verify, com o
  // header de locale setado para que o age gate renderize no idioma correto.
  // A rota fisica e `app/age-verify/page.tsx` sem segmento [locale].
  if (prefixedLocale && stripped === "/age-verify") {
    const rewriteUrl = request.nextUrl.clone();
    rewriteUrl.pathname = "/age-verify";
    const requestHeaders = withLocaleHeader(request, prefixedLocale);
    const response = NextResponse.rewrite(rewriteUrl, {
      request: { headers: requestHeaders },
    });
    return copyGeoHeader(request, response);
  }

  if (isBypassPath(pathname)) {
    return NextResponse.next();
  }

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

  // F9.9 (DECISIONS #19) - locale publico desligado em link indexado.
  // Quando um prefixo /en, /es, /fr aparece em share link /c/:id mas o
  // locale correspondente nao esta em STATICALLY_ENABLED_LOCALES, emitir
  // 301 permanente para a rota sem prefixo, preservando o slug do share.
  // Isso mantem SEO (Google propaga pro novo link), evita 404, e evita
  // fallback silencioso com idioma diferente. Aplicado SOMENTE em share
  // routes (/c/:id). Demais rotas SEO continuam com rewrite para respeitar
  // preferencia declarada pelo usuario.
  if (
    prefixedLocale &&
    !STATICALLY_ENABLED_LOCALES.includes(prefixedLocale) &&
    /^\/c\/[^/]+\/?$/.test(targetPath)
  ) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = targetPath;
    return NextResponse.redirect(redirectUrl, 301);
  }

  const locale: SupportedLocale =
    prefixedLocale ?? resolveLocaleFromRequest(request);

  const requestHeaders = withLocaleHeader(request, locale);

  let response: NextResponse;
  if (prefixedLocale) {
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

// F2.5b + F7.6 - Matcher allowlist explicito.
//
// Acrescentado em F7.6: rotas gated (`/`, `/chat/:path*`, `/conta`,
// `/favoritos`, `/plano`) para que o middleware receba esses paths e
// possa acionar o age gate. `/age-verify` e `/legal/*` intencionalmente
// NAO entram (publicos; primeiro libera o gate; segundo e leitura legal).
export const config = {
  matcher: [
    // F7.6 gated paths
    "/",
    "/chat/:path*",
    "/conta",
    "/conta/:path*",
    "/favoritos",
    "/favoritos/:path*",
    "/plano",
    "/plano/:path*",
    // F2.5 public SEO (sem prefixo)
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
    "/en/chat/:path*",
    "/en/conta",
    "/en/conta/:path*",
    "/en/favoritos",
    "/en/favoritos/:path*",
    "/en/plano",
    "/en/plano/:path*",
    "/en/age-verify",
    // Prefixo /es
    "/es/ajuda",
    "/es/privacy",
    "/es/terms",
    "/es/data-deletion",
    "/es/welcome",
    "/es/c/:id",
    "/es/chat/:path*",
    "/es/conta",
    "/es/conta/:path*",
    "/es/favoritos",
    "/es/favoritos/:path*",
    "/es/plano",
    "/es/plano/:path*",
    "/es/age-verify",
    // Prefixo /fr
    "/fr/ajuda",
    "/fr/privacy",
    "/fr/terms",
    "/fr/data-deletion",
    "/fr/welcome",
    "/fr/c/:id",
    "/fr/chat/:path*",
    "/fr/conta",
    "/fr/conta/:path*",
    "/fr/favoritos",
    "/fr/favoritos/:path*",
    "/fr/plano",
    "/fr/plano/:path*",
    "/fr/age-verify",
  ],
};
