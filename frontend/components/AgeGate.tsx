"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

const COOKIE_NAME = "wg_age_verified";
const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365; // 1 ano

// F7.6 - Formato do cookie wg_age_verified:
//   "<MARKET>:<MIN_AGE>:<ISO_TIMESTAMP>"
// Ex: "BR:18:2026-04-22T00:00:00.000Z"
// O middleware usa a existencia + parseabilidade do cookie como gate.
function writeAgeVerifiedCookie(market: string, minAge: number): void {
  if (typeof document === "undefined") return;
  const timestamp = new Date().toISOString();
  const raw = `${market}:${minAge}:${timestamp}`;
  const value = encodeURIComponent(raw);
  document.cookie =
    `${COOKIE_NAME}=${value}; path=/; max-age=${COOKIE_MAX_AGE_SECONDS}; samesite=lax`;
}

interface AgeGateProps {
  market: string;
  minimumAge: number;
  /** Caminho a navegar apos confirmacao bem sucedida. Default "/". */
  next?: string;
  /** Link interno para os termos no mesmo locale/mercado. */
  termsHref: string;
  /** Link interno para a privacy no mesmo locale/mercado. */
  privacyHref: string;
}

export function AgeGate({
  market,
  minimumAge,
  next,
  termsHref,
  privacyHref,
}: AgeGateProps) {
  const t = useTranslations("ageGate");
  const [denied, setDenied] = useState(false);

  if (denied) {
    return (
      <section className="text-center max-w-md mx-auto">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-3">
          {t("deniedTitle")}
        </h1>
        <p className="text-wine-muted text-sm">
          {t("deniedBody", { age: minimumAge })}
        </p>
      </section>
    );
  }

  const handleConfirm = () => {
    writeAgeVerifiedCookie(market, minimumAge);
    const target = next && next.startsWith("/") ? next : "/";
    // Navegacao hard para forcar o middleware a re-avaliar o cookie e
    // liberar a rota destino sem cache de rota stale.
    window.location.href = target;
  };

  return (
    <section className="text-center max-w-md mx-auto">
      <h1 className="font-display text-2xl font-bold text-wine-text mb-3">
        {t("title")}
      </h1>
      <p className="text-wine-muted text-sm mb-6">
        {t("subtitle", { age: minimumAge })}
      </p>
      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={handleConfirm}
          className="px-5 py-2.5 rounded-lg bg-wine-accent text-white text-sm font-medium hover:opacity-90 transition-opacity"
        >
          {t("confirmCta", { age: minimumAge })}
        </button>
        <button
          type="button"
          onClick={() => setDenied(true)}
          className="px-5 py-2.5 rounded-lg border border-wine-border text-wine-text text-sm hover:bg-wine-surface transition-colors"
        >
          {t("denyCta", { age: minimumAge })}
        </button>
      </div>
      <p className="text-wine-muted text-xs mt-6">
        {t.rich("legalLink", {
          terms: (chunks) => (
            <Link href={termsHref} className="text-wine-accent underline">
              {chunks}
            </Link>
          ),
          privacy: (chunks) => (
            <Link href={privacyHref} className="text-wine-accent underline">
              {chunks}
            </Link>
          ),
        })}
      </p>
    </section>
  );
}
