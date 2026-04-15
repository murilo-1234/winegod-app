"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { LoginButton } from "@/components/auth/LoginButton";
import { useAuth } from "@/lib/useAuth";
import {
  fetchSavedConversations,
  type ConversationSummary,
} from "@/lib/conversations";

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
        Entre para ver seus favoritos
      </h2>
      <p className="text-wine-muted text-sm mb-6 max-w-sm mx-auto">
        Faca login para salvar e acessar suas conversas favoritas.
      </p>
      <LoginButton />
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message?: string;
  onRetry: () => void;
}) {
  return (
    <div className="text-center py-12">
      <p className="text-wine-muted text-sm mb-2">
        {message || "Nao foi possivel carregar seus favoritos."}
      </p>
      <button
        onClick={onRetry}
        className="text-wine-accent text-sm hover:underline"
      >
        Tentar novamente
      </button>
    </div>
  );
}

function EmptyState() {
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
        Nenhuma conversa salva
      </h2>
      <p className="text-wine-muted text-sm max-w-sm mx-auto">
        Quando voce salvar uma conversa no chat, ela aparecera aqui.
      </p>
    </div>
  );
}

function formatSavedDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  try {
    return new Date(dateStr).toLocaleDateString("pt-BR", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

function getConversationTitle(conv: ConversationSummary): string {
  const title = conv.title?.trim();
  return title || "Conversa sem titulo";
}

export function FavoritosContent() {
  const { user, loading: authLoading, error: authError } = useAuth();
  const router = useRouter();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

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

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-4 py-8 overflow-y-auto h-full">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-6">
          Conversas salvas
        </h1>
        {authLoading || loading ? (
          <LoadingSkeleton />
        ) : authError ? (
          <ErrorState
            message="Nao foi possivel verificar sua conta."
            onRetry={() => window.location.reload()}
          />
        ) : error ? (
          <ErrorState onRetry={loadSaved} />
        ) : !user ? (
          <GuestState />
        ) : conversations.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-2">
            {conversations.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => router.push(`/chat/${conv.id}`)}
                  className="w-full text-left px-4 py-3 rounded-xl bg-wine-surface hover:bg-wine-surface/80 transition-colors"
                >
                  <p className="text-sm text-wine-text font-medium truncate">
                    {getConversationTitle(conv)}
                  </p>
                  {conv.saved_at && (
                    <p className="text-xs text-wine-muted mt-0.5">
                      Salva em {formatSavedDate(conv.saved_at)}
                    </p>
                  )}
                </button>
              ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
