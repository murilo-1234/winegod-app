"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Heart } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { LoginButton } from "@/components/auth/LoginButton";
import { useAuth } from "@/lib/useAuth";
import {
  fetchSavedConversations,
  updateConversationSaved,
  type ConversationSummary,
} from "@/lib/conversations";
import { formatDate as i18nFormatDate } from "@/lib/i18n/formatters";

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-16 bg-wine-surface rounded-xl" />
      ))}
    </div>
  );
}

function GuestState() {
  const t = useTranslations("favorites");
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
          <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
        </svg>
      </div>
      <h2 className="font-display text-lg font-bold text-wine-text mb-2">
        {t("guest.title")}
      </h2>
      <p className="text-wine-muted text-sm mb-6 max-w-sm mx-auto">
        {t("guest.description")}
      </p>
      <LoginButton />
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  const t = useTranslations("favorites");
  return (
    <div className="text-center py-12">
      <p className="text-wine-muted text-sm mb-2">{message}</p>
      <button
        onClick={onRetry}
        className="text-wine-accent text-sm hover:underline"
      >
        {t("error.retry")}
      </button>
    </div>
  );
}

function EmptyState() {
  const t = useTranslations("favorites");
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
          <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
        </svg>
      </div>
      <h2 className="font-display text-lg font-bold text-wine-text mb-2">
        {t("empty.title")}
      </h2>
      <p className="text-wine-muted text-sm max-w-sm mx-auto">
        {t("empty.description")}
      </p>
    </div>
  );
}

function formatSavedDate(
  dateStr: string | null | undefined,
  locale: string,
): string {
  if (!dateStr) return "";
  try {
    return i18nFormatDate(dateStr, locale, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

export function FavoritosContent() {
  const t = useTranslations("favorites");
  const locale = useLocale();
  const { user, loading: authLoading, error: authError } = useAuth();
  const router = useRouter();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<{
    kind: "removed" | "error";
    text: string;
  } | null>(null);
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showNotice = useCallback(
    (kind: "removed" | "error", text: string) => {
      setNotice({ kind, text });
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
      noticeTimerRef.current = setTimeout(() => setNotice(null), 2200);
    },
    []
  );

  useEffect(() => {
    return () => {
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
    };
  }, []);

  const loadSaved = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const list = await fetchSavedConversations();
      setConversations(list);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) loadSaved();
  }, [user, loadSaved]);

  const getConversationTitle = useCallback(
    (conv: ConversationSummary): string => {
      const title = conv.title?.trim();
      return title || t("untitled");
    },
    [t],
  );

  const handleUnsave = useCallback(
    async (id: string) => {
      if (pendingIds.has(id)) return;
      const previous = conversations;
      // Optimistic remove
      setConversations((prev) => prev.filter((c) => c.id !== id));
      setPendingIds((prev) => {
        const next = new Set(prev);
        next.add(id);
        return next;
      });

      const ok = await updateConversationSaved(id, false);

      setPendingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });

      if (ok) {
        showNotice("removed", t("notice.removed"));
      } else {
        // Rollback
        setConversations(previous);
        showNotice("error", t("notice.error"));
      }
    },
    [conversations, pendingIds, showNotice, t]
  );

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-4 py-8 overflow-y-auto h-full">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-6">
          {t("heading")}
        </h1>
        {authLoading || loading ? (
          <LoadingSkeleton />
        ) : authError ? (
          <ErrorState
            message={t("error.auth")}
            onRetry={() => window.location.reload()}
          />
        ) : error ? (
          <ErrorState message={t("error.default")} onRetry={loadSaved} />
        ) : !user ? (
          <GuestState />
        ) : conversations.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-2">
            {conversations.map((conv) => {
              const isPending = pendingIds.has(conv.id);
              const savedDate = formatSavedDate(conv.saved_at, locale);
              return (
                <div
                  key={conv.id}
                  className="group flex items-center gap-2 px-4 py-3 rounded-xl bg-wine-surface hover:bg-wine-surface/80 transition-colors"
                >
                  <button
                    onClick={() => router.push(`/chat/${conv.id}`)}
                    className="flex-1 min-w-0 text-left"
                  >
                    <p className="text-sm text-wine-text font-medium truncate">
                      {getConversationTitle(conv)}
                    </p>
                    {savedDate && (
                      <p className="text-xs text-wine-muted mt-0.5">
                        {t("savedOn", { date: savedDate })}
                      </p>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleUnsave(conv.id);
                    }}
                    disabled={isPending}
                    className={`flex-shrink-0 p-2 rounded-full transition-colors ${
                      isPending
                        ? "opacity-50 cursor-not-allowed"
                        : "hover:bg-red-50"
                    }`}
                    aria-label={t("removeAria")}
                    title={t("removeAria")}
                  >
                    <Heart
                      size={18}
                      strokeWidth={1.8}
                      className="text-red-500"
                      fill="currentColor"
                    />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {notice && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50"
          aria-live="polite"
        >
          <div
            className={`rounded-full border px-4 py-2 text-sm font-medium shadow-lg backdrop-blur ${
              notice.kind === "error"
                ? "border-red-200 bg-red-50 text-red-600"
                : "border-wine-border bg-white/95 text-wine-text"
            }`}
          >
            {notice.text}
          </div>
        </div>
      )}
    </AppShell>
  );
}
