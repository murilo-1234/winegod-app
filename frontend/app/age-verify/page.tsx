import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { cookies, headers } from "next/headers";
import { getLocale, getTranslations } from "next-intl/server";
import { AgeGate } from "@/components/AgeGate";
import {
  deriveMarketFromLocale,
  getMarketAgeGate,
  normalizeMarketCountry,
} from "@/lib/i18n/markets";
import { buildLegalPath } from "@/lib/legal-routing";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ageGate");
  return {
    title: `${t("title")} — winegod.ai`,
  };
}

function resolveDocHrefs(locale: string): {
  termsHref: string;
  privacyHref: string;
} {
  return {
    termsHref: buildLegalPath(locale, "terms"),
    privacyHref: buildLegalPath(locale, "privacy"),
  };
}

function pickMarket(
  geoCountry: string | undefined,
  cookieLocale: string | undefined,
): string {
  if (geoCountry && /^[A-Z]{2}$/.test(geoCountry.toUpperCase())) {
    return normalizeMarketCountry(geoCountry);
  }
  if (cookieLocale) {
    return deriveMarketFromLocale(cookieLocale);
  }
  return "DEFAULT";
}

export default async function AgeVerifyPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const rawNext = Array.isArray(sp.next) ? sp.next[0] : sp.next;
  // Aceitamos apenas paths internos absolutos para evitar open redirect.
  const next =
    typeof rawNext === "string" && rawNext.startsWith("/") && !rawNext.startsWith("//")
      ? rawNext
      : "/";

  const cookieStore = await cookies();
  const headerStore = await headers();

  const geoCountry = (
    headerStore.get("x-vercel-ip-country") ??
    headerStore.get("X-Vercel-IP-Country") ??
    ""
  ).toUpperCase();
  const cookieLocale = cookieStore.get("wg_locale_choice")?.value;

  const market = pickMarket(geoCountry || undefined, cookieLocale);
  const policy = getMarketAgeGate(market);

  if (!policy.required) {
    // Mercado sem gate: segue direto para o destino pedido.
    redirect(next);
  }

  const docLocale = await getLocale();
  const { termsHref, privacyHref } = resolveDocHrefs(docLocale);

  return (
    <main className="min-h-dvh bg-wine-bg flex items-center justify-center px-4 py-8">
      <AgeGate
        market={market}
        minimumAge={policy.minimumAge}
        next={next}
        termsHref={termsHref}
        privacyHref={privacyHref}
      />
    </main>
  );
}
