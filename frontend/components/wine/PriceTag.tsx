"use client";

import { useLocale, useTranslations } from "next-intl";

interface PriceTagProps {
  precoMin: number | null;
  precoMax: number | null;
  moeda: string;
}

function formatCurrency(value: number, moeda: string, locale: string): string {
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: moeda,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${moeda} ${value}`;
  }
}

export function PriceTag({ precoMin, precoMax, moeda }: PriceTagProps) {
  const t = useTranslations("priceTag");
  const locale = useLocale();

  if (precoMin == null && precoMax == null) {
    return <span className="text-sm text-wine-muted">{t("unavailable")}</span>;
  }

  const min = precoMin ?? precoMax!;
  const max = precoMax ?? precoMin!;

  return (
    <span className="text-sm font-semibold text-wine-accent">
      {min === max
        ? formatCurrency(min, moeda, locale)
        : `${formatCurrency(min, moeda, locale)} - ${formatCurrency(max, moeda, locale)}`}
    </span>
  );
}
