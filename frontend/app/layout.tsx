import type { Metadata } from "next";
import { Inter, Playfair_Display } from "next/font/google";
import { headers } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages, getTranslations } from "next-intl/server";
import { LocaleProvider } from "@/lib/i18n/locale-context";
import { AnalyticsProvider } from "@/lib/observability/analytics-provider";
import { handleIntlError } from "@/lib/observability/intl-error-handler";
import { defaultLocale, isAppLocale, type AppLocale } from "@/i18n/routing";
import { deriveMarketFromLocale } from "@/lib/i18n/markets";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });
const playfair = Playfair_Display({
  subsets: ["latin"],
  weight: ["700", "900"],
  variable: "--font-display",
});

// F4.1 - Metadata dinamica via next-intl. Le chaves `metadata.root.*`
// das messages do locale ativo; fallback chain de F2.4 cobre quando o
// locale nao tem chave (es-419/fr-FR caem em en-US e depois pt-BR).
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("metadata.root");
  const title = t("title");
  const description = t("description");
  const siteName = t("siteName");
  const url = t("url");

  return {
    title,
    description,
    icons: { icon: "/favicon.ico" },
    openGraph: {
      title,
      description,
      type: "website",
      url,
      siteName,
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // F2.3b: locale e messages vem do request config (frontend/i18n/request.ts).
  // F2.4 substituira o stub por resolucao real (cookie wg_locale_choice,
  // header geo, fallback chain). Nesta fase, garante que useTranslations()
  // funciona em todas as rotas sem prefixo (/, /chat/[id], /conta, etc.).
  const locale = await getLocale();
  const messages = await getMessages();

  // F2.9a: seed do LocaleProvider com o que o server ja resolveu.
  // Provider client-side hidrata o cookie wg_locale_choice depois.
  const seedLocale: AppLocale = isAppLocale(locale) ? locale : defaultLocale;
  const seedMarket = deriveMarketFromLocale(seedLocale);

  // F2.9c2: le X-Vercel-IP-Country do request atual para seedar o
  // geoCountry no contexto (consumido pelo LocaleSuggestionBanner).
  // Header ausente em dev local -> null; banner nao aparece.
  const headerStore = await headers();
  const geoRaw =
    headerStore.get("x-vercel-ip-country") ??
    headerStore.get("X-Vercel-IP-Country");
  const seedGeo = geoRaw ? geoRaw.toUpperCase() : null;

  return (
    <html lang={locale}>
      <body className={`${inter.className} ${playfair.variable}`}>
        <NextIntlClientProvider
          locale={locale}
          messages={messages}
          onError={handleIntlError}
        >
          <LocaleProvider
            initialUiLocale={seedLocale}
            initialMarketCountry={seedMarket}
            initialGeoCountry={seedGeo}
          >
            <AnalyticsProvider>{children}</AnalyticsProvider>
          </LocaleProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
