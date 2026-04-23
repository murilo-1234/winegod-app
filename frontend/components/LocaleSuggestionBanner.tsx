"use client";

// F2.9c2 - Banner de sugestao de troca de idioma.
//
// Apareca SOMENTE quando:
//   1. geoCountry (X-Vercel-IP-Country seed do server) e conhecido e
//      mapeia para um locale Tier 1.
//   2. wg_locale_choice cookie NAO existe (sem escolha manual previa).
//   3. locale sugerido != uiLocale atual.
//   4. locale sugerido esta em `useEnabledLocales().locales` (kill switch).
//
// Nunca redireciona. Aceitar -> setUiLocale() + cookie via F2.9a.
// Dispensar -> marca sessionStorage (sem cookie novo).

import { useEffect, useMemo, useState } from "react";

import { type AppLocale, isAppLocale } from "@/i18n/routing";
import { readLocaleCookie } from "@/lib/i18n/cookie";
import { useLocaleContext } from "@/lib/i18n/locale-context";
import { useEnabledLocales } from "@/lib/i18n/useEnabledLocales";

const DISMISS_SESSION_KEY = "wg_locale_suggestion_dismissed";

// Copy curto por locale Tier 1. NAO usa messages/*.json nesta fase.
// Quando Onda 4/F4.x popular traducoes reais, migrar para `useTranslations`.
interface BannerCopy {
  prompt: (native: string) => string;
  accept: string;
  dismiss: string;
}

const COPY_BY_LOCALE: Record<AppLocale, BannerCopy> = {
  "pt-BR": {
    prompt: (native) => `Quer continuar em ${native}?`,
    accept: "Trocar idioma",
    dismiss: "Manter assim",
  },
  "en-US": {
    prompt: (native) => `Continue in ${native}?`,
    accept: "Switch language",
    dismiss: "Keep as is",
  },
  "es-419": {
    prompt: (native) => `Continuar en ${native}?`,
    accept: "Cambiar idioma",
    dismiss: "Mantener",
  },
  "fr-FR": {
    prompt: (native) => `Continuer en ${native} ?`,
    accept: "Changer la langue",
    dismiss: "Garder",
  },
};

const NATIVE_NAME: Record<AppLocale, string> = {
  "pt-BR": "Portugues",
  "en-US": "English",
  "es-419": "Espanol",
  "fr-FR": "Francais",
};

// Geo -> locale Tier 1 sugerido. Mantemos aqui porque este e o unico
// lugar que traduz geo em sugestao; nao vale centralizar ainda.
const SUGGESTED_LOCALE_BY_COUNTRY: Record<string, AppLocale> = {
  BR: "pt-BR",
  US: "en-US",
  MX: "es-419",
  AR: "es-419",
  CO: "es-419",
  CL: "es-419",
  PE: "es-419",
  ES: "es-419",
  FR: "fr-FR",
};

function readDismissed(): boolean {
  if (typeof sessionStorage === "undefined") return false;
  try {
    return sessionStorage.getItem(DISMISS_SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

function writeDismissed(): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(DISMISS_SESSION_KEY, "1");
  } catch {
    // storage cheio / modo privado: ignorar. Banner some pelo state local.
  }
}

export function LocaleSuggestionBanner() {
  const { uiLocale, geoCountry, setUiLocale } = useLocaleContext();
  const { locales: enabledLocales, isLoading: enabledLoading } =
    useEnabledLocales();

  // 1. se ja houver cookie manual, nunca mostra.
  // 2. se ja dispensado nesta sessao, nunca mostra.
  // Ambos sao resolvidos client-side apos mount (evita hydration mismatch).
  const [mounted, setMounted] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [hasManualCookie, setHasManualCookie] = useState(false);

  useEffect(() => {
    setMounted(true);
    setHasManualCookie(readLocaleCookie() !== null);
    setDismissed(readDismissed());
  }, []);

  const suggestedLocale = useMemo<AppLocale | null>(() => {
    if (!geoCountry) return null;
    const loc = SUGGESTED_LOCALE_BY_COUNTRY[geoCountry];
    return loc && isAppLocale(loc) ? loc : null;
  }, [geoCountry]);

  const shouldShow = useMemo(() => {
    if (!mounted) return false;
    if (dismissed) return false;
    if (hasManualCookie) return false;
    if (!suggestedLocale) return false;
    if (suggestedLocale === uiLocale) return false;
    if (enabledLoading) return false;
    if (!enabledLocales.includes(suggestedLocale)) return false;
    return true;
  }, [
    mounted,
    dismissed,
    hasManualCookie,
    suggestedLocale,
    uiLocale,
    enabledLoading,
    enabledLocales,
  ]);

  if (!shouldShow || !suggestedLocale) return null;

  // Copy na lingua SUGERIDA (melhor reconhecimento pelo usuario alvo).
  const copy = COPY_BY_LOCALE[suggestedLocale];
  const native = NATIVE_NAME[suggestedLocale];

  const handleAccept = () => {
    setUiLocale(suggestedLocale);
    // Nao grava dismiss: o cookie wg_locale_choice agora existe e o
    // proprio shouldShow passa a retornar false nas proximas renders.
  };

  const handleDismiss = () => {
    writeDismissed();
    setDismissed(true);
  };

  return (
    <div
      role="region"
      aria-label="Language suggestion"
      className="border-b border-wine-border bg-wine-surface/60"
    >
      <div className="max-w-3xl mx-auto px-4 py-2 flex items-center gap-3 text-sm">
        <span className="flex-1 text-wine-muted truncate">
          {copy.prompt(native)}
        </span>
        <button
          type="button"
          onClick={handleAccept}
          className="px-3 py-1 rounded-md bg-wine-accent text-wine-bg text-xs font-medium hover:opacity-90 transition-opacity"
        >
          {copy.accept}
        </button>
        <button
          type="button"
          onClick={handleDismiss}
          className="px-2 py-1 rounded-md text-xs text-wine-muted hover:text-wine-fg transition-colors"
          aria-label={copy.dismiss}
        >
          {copy.dismiss}
        </button>
      </div>
    </div>
  );
}
