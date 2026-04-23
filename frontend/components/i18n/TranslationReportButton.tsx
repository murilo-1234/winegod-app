"use client";

// F11.4 - Affordance minima para `translation_report_submitted`.
//
// Sem backend novo, sem ticketing, sem backoffice. Quando o usuario clica,
// o componente:
//   1. Pede uma descricao curta via `window.prompt(...)` (discreto, nativo).
//   2. Se houver descricao, captura evento PostHog com locale atual + path +
//      texto.
//   3. Nao faz request HTTP para nenhum backend proprio. PostHog e a sink.
//
// Esta affordance e deliberadamente discreta para nao ampliar escopo
// (Rally 5 §3.5). Quando o operator quiser um fluxo rico (form dedicado,
// anexos, roteamento para Linear/Jira), fica para um rally posterior.

import { useTranslations } from "next-intl";

import { useLocaleContext } from "@/lib/i18n/locale-context";
import { capture } from "@/lib/observability/posthog";

interface TranslationReportButtonProps {
  className?: string;
}

export function TranslationReportButton({
  className,
}: TranslationReportButtonProps) {
  const t = useTranslations("translationReport");
  const { uiLocale, marketCountry } = useLocaleContext();

  const handleClick = () => {
    if (typeof window === "undefined") return;
    const description = window.prompt(t("promptLabel"));
    if (!description || !description.trim()) return;

    capture("translation_report_submitted", {
      locale: uiLocale,
      market_country: marketCountry,
      route: window.location.pathname,
      description: description.trim().slice(0, 500),
    });

    try {
      window.alert(t("thanks"));
    } catch {
      // no-op
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={
        className ??
        "px-2 py-1 text-xs text-wine-muted hover:text-wine-text underline decoration-dotted"
      }
      title={t("title")}
    >
      {t("cta")}
    </button>
  );
}
