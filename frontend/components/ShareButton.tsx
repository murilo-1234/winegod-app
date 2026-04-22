"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface ShareButtonProps {
  wine_ids: number[];
  title?: string;
  context?: string;
}

export function ShareButton({ wine_ids, title, context }: ShareButtonProps) {
  const t = useTranslations("shareButton");
  const [status, setStatus] = useState<"idle" | "loading" | "copied" | "error">(
    "idle"
  );

  async function handleShare() {
    if (status === "loading") return;
    setStatus("loading");

    try {
      const res = await fetch(`${API_URL}/api/share`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wine_ids, title, context }),
      });

      if (!res.ok) {
        setStatus("error");
        setTimeout(() => setStatus("idle"), 3000);
        return;
      }

      const data = await res.json();
      await navigator.clipboard.writeText(data.url);
      setStatus("copied");
      setTimeout(() => setStatus("idle"), 3000);
    } catch {
      setStatus("error");
      setTimeout(() => setStatus("idle"), 3000);
    }
  }

  const label = t(status);

  return (
    <button
      onClick={handleShare}
      disabled={status === "loading"}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
        status === "copied"
          ? "border-green-600 text-green-400"
          : status === "error"
            ? "border-red-600 text-red-400"
            : "border-wine-accent text-wine-accent hover:bg-wine-accent/10"
      } disabled:opacity-50`}
    >
      {/* Share icon */}
      <svg
        className="w-3.5 h-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {status === "copied" ? (
          <path d="M20 6L9 17l-5-5" />
        ) : (
          <>
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </>
        )}
      </svg>
      {label}
    </button>
  );
}
