"use client";

import { useTranslations } from "next-intl";
import { LoginButton } from "./LoginButton";

interface CreditsBannerProps {
  isLoggedIn: boolean;
  reason: "guest_limit" | "daily_limit";
}

export function CreditsBanner({ isLoggedIn, reason }: CreditsBannerProps) {
  const t = useTranslations("creditsBanner");
  return (
    <div className="mx-4 mb-2 p-4 rounded-xl bg-wine-surface border border-wine-accent/30 text-center">
      <p className="text-wine-text text-sm mb-1">
        {t("title")}
      </p>

      {reason === "guest_limit" && !isLoggedIn ? (
        <div className="mt-3">
          <p className="text-wine-muted text-xs mb-3">
            {t("guestCta")}
          </p>
          <LoginButton />
        </div>
      ) : (
        <p className="text-wine-muted text-xs">
          {t("dailyReset")}
        </p>
      )}
    </div>
  );
}
