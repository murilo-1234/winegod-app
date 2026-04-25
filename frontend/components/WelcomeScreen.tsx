"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Camera, Wine, ClipboardList, Store, Scale, FileText } from "lucide-react";

type Period = "madrugada" | "manha" | "tarde" | "noite";
type Weekday = "sun" | "mon" | "tue" | "wed" | "thu" | "fri" | "sat";

const WEEKDAYS: readonly Weekday[] = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

function resolvePeriod(hour: number): Period {
  if (hour < 6) return "madrugada";
  if (hour < 12) return "manha";
  if (hour < 18) return "tarde";
  return "noite";
}

function resolveWeekday(day: number): Weekday {
  return WEEKDAYS[day] ?? "sun";
}

const CARD_ICONS = [Camera, Wine, ClipboardList, Store, Scale, FileText] as const;
const CARD_COUNT = CARD_ICONS.length;

interface WelcomeScreenProps {
  onSuggestionClick: (text: string) => void;
  userName?: string;
  chatInputSlot?: React.ReactNode;
}

export function WelcomeScreen({ onSuggestionClick, userName, chatInputSlot }: WelcomeScreenProps) {
  const t = useTranslations("welcome");
  const [greeting, setGreeting] = useState<string>(() => t("greetingFallback"));

  useEffect(() => {
    const now = new Date();
    const period = resolvePeriod(now.getHours());
    const weekday = resolveWeekday(now.getDay());
    const firstName = userName?.trim().split(/\s+/)[0];
    const resolved = firstName
      ? t(`greeting.${period}.named`, { weekday, name: firstName })
      : t(`greeting.${period}.guest`, { weekday });
    setGreeting(resolved);
  }, [userName, t]);

  const cards = Array.from({ length: CARD_COUNT }, (_, i) => ({
    Icon: CARD_ICONS[i],
    title: t(`cards.${i + 1}.title`),
    prompt: t(`cards.${i + 1}.prompt`),
  }));

  const topRow = cards.slice(0, 4);
  const bottomRow = cards.slice(4, 6);

  return (
    <div className="flex-1 flex flex-col">
      {/* Greeting - centered */}
      <div className="flex-1 flex flex-col items-center justify-center px-6">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-3">
          {greeting}
        </h1>
        <p className="text-wine-muted text-sm leading-relaxed text-center max-w-md">
          {t("subtitle")}
        </p>
      </div>

      {/* Chat input slot - between greeting and cards */}
      {chatInputSlot && (
        <div className="px-4 pb-3">
          {chatInputSlot}
        </div>
      )}

      {/* Cards - bottom, below input (style Gemini) */}
      <div className="px-4 pb-3">
        <div className="w-full max-w-xl mx-auto">
          {/* Top row: 4 cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {topRow.map(({ Icon, title, prompt }) => (
              <button
                key={title}
                type="button"
                onClick={() => onSuggestionClick(prompt)}
                className="flex flex-col items-center gap-1 px-3 py-1.5 rounded-xl bg-wine-surface border border-wine-border hover:border-wine-accent hover:bg-wine-accent/5 transition-colors"
              >
                <Icon size={22} className="text-wine-accent" />
                <span className="text-xs font-medium text-wine-text text-center">
                  {title}
                </span>
              </button>
            ))}
          </div>

          {/* Bottom row: 2 cards centered */}
          <div className="grid grid-cols-2 gap-3 mt-3 max-w-[calc(50%+6px)] mx-auto">
            {bottomRow.map(({ Icon, title, prompt }) => (
              <button
                key={title}
                type="button"
                onClick={() => onSuggestionClick(prompt)}
                className="flex flex-col items-center gap-1 px-3 py-1.5 rounded-xl bg-wine-surface border border-wine-border hover:border-wine-accent hover:bg-wine-accent/5 transition-colors"
              >
                <Icon size={22} className="text-wine-accent" />
                <span className="text-xs font-medium text-wine-text text-center">
                  {title}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
