"use client";

import { useTranslations } from "next-intl";
import { AppShell } from "@/components/AppShell";
import { LoginButton } from "@/components/auth/LoginButton";
import { useAuth } from "@/lib/useAuth";
import type { AuthResponse } from "@/lib/auth";

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-4 bg-wine-surface rounded w-1/4" />
      <div className="h-3 bg-wine-surface rounded w-full" />
      <div className="h-3 bg-wine-surface rounded w-1/2" />
    </div>
  );
}

function GuestState() {
  const t = useTranslations("plan");
  return (
    <div className="text-center py-12">
      <div className="w-16 h-16 rounded-full bg-wine-surface flex items-center justify-center mx-auto mb-4">
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="text-wine-muted"
        >
          <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
          <line x1="1" y1="10" x2="23" y2="10" />
        </svg>
      </div>
      <h2 className="font-display text-lg font-bold text-wine-text mb-2">
        {t("guest.title")}
      </h2>
      <p className="text-wine-muted text-sm mb-2 max-w-sm mx-auto">
        {t.rich("guest.sessionLimit", {
          b: (chunks) => (
            <strong className="text-wine-text">{chunks}</strong>
          ),
        })}
      </p>
      <p className="text-wine-muted text-sm mb-6 max-w-sm mx-auto">
        {t.rich("guest.loggedLimit", {
          b: (chunks) => (
            <strong className="text-wine-text">{chunks}</strong>
          ),
        })}
      </p>
      <LoginButton />
    </div>
  );
}

function ErrorState() {
  const t = useTranslations("plan");
  return (
    <div className="text-center py-12">
      <p className="text-wine-muted text-sm mb-2">
        {t("error.message")}
      </p>
      <button
        onClick={() => window.location.reload()}
        className="text-wine-accent text-sm underline"
      >
        {t("error.retry")}
      </button>
    </div>
  );
}

const COST_ROWS: { key: "text" | "onePhoto" | "fewPhotos" | "video" | "pdf"; count: number }[] = [
  { key: "text", count: 1 },
  { key: "onePhoto", count: 1 },
  { key: "fewPhotos", count: 3 },
  { key: "video", count: 3 },
  { key: "pdf", count: 3 },
];

function PlanDetails({ credits }: { credits: AuthResponse["credits"] }) {
  const t = useTranslations("plan");
  const remaining = Math.max(0, credits.limit - credits.used);
  const pct = credits.limit > 0 ? (remaining / credits.limit) * 100 : 0;

  return (
    <>
      {/* Current plan */}
      <div className="bg-wine-surface rounded-xl p-5 mb-6">
        <div className="flex items-center justify-between mb-1">
          <span className="text-wine-text text-sm font-semibold">
            {t("planLabel")}
          </span>
          <span className="text-wine-muted text-xs bg-wine-bg px-2 py-0.5 rounded">
            {t("statusActive")}
          </span>
        </div>
        <p className="text-wine-muted text-xs">
          {t("planDescription")}
        </p>
      </div>

      {/* Credits bar */}
      <div className="mb-8">
        <div className="flex items-baseline justify-between mb-2">
          <span className="text-wine-text text-sm font-semibold">
            {t("creditsToday")}
          </span>
          <span className="text-wine-muted text-sm">
            {t("remainingOfLimit", { remaining, limit: credits.limit })}
          </span>
        </div>
        <div className="h-2.5 rounded-full bg-wine-surface overflow-hidden">
          <div
            className="h-full rounded-full bg-wine-accent transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-wine-muted text-xs mt-2">
          {t("usedToday", { count: credits.used })}
        </p>
      </div>

      {/* Cost table */}
      <div className="mb-8">
        <h2 className="text-wine-text text-sm font-semibold mb-3">
          {t("cost.header")}
        </h2>
        <div className="bg-wine-surface rounded-xl divide-y divide-wine-border">
          {COST_ROWS.map((row) => (
            <div
              key={row.key}
              className="flex justify-between px-4 py-2.5 text-sm"
            >
              <span className="text-wine-text">{t(`cost.${row.key}`)}</span>
              <span className="text-wine-muted">
                {t("cost.credits", { count: row.count })}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Pro teaser */}
      <div className="border border-dashed border-wine-border rounded-xl p-5">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-wine-accent text-sm font-semibold">
            {t("pro.badge")}
          </span>
        </div>
        <ul className="text-wine-muted text-sm space-y-1">
          <li>{t("pro.feature1")}</li>
          <li>{t("pro.feature2")}</li>
          <li>{t("pro.feature3")}</li>
        </ul>
        <p className="text-wine-muted text-xs mt-3">
          {t("pro.note")}
        </p>
      </div>
    </>
  );
}

export function PlanoContent() {
  const t = useTranslations("plan");
  const { user, credits, loading, error } = useAuth();

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-4 py-8 overflow-y-auto h-full">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-6">
          {t("heading")}
        </h1>
        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorState />
        ) : !user || !credits ? (
          <GuestState />
        ) : (
          <PlanDetails credits={credits} />
        )}
      </div>
    </AppShell>
  );
}
