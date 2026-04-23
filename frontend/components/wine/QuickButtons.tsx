"use client";

import { useTranslations } from "next-intl";

interface QuickButtonsProps {
  onAction: (text: string) => void;
}

const ACTION_KEYS = ["compare", "similar", "cheaper", "whereToBuy"] as const;

export function QuickButtons({ onAction }: QuickButtonsProps) {
  const t = useTranslations("quickButtons");
  return (
    <div className="flex gap-2 overflow-x-auto py-2">
      {ACTION_KEYS.map((key) => (
        <button
          key={key}
          onClick={() => onAction(t(`${key}.message`))}
          className="flex-shrink-0 px-3 py-1.5 text-xs rounded-full border border-wine-accent text-wine-accent hover:bg-wine-accent/10 transition-colors whitespace-nowrap"
        >
          {t(`${key}.label`)}
        </button>
      ))}
    </div>
  );
}
