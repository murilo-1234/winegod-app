"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Search, Heart, MessageCircle } from "lucide-react";
import {
  searchConversations,
  fetchSavedConversations,
  type ConversationSummary,
} from "@/lib/conversations";

interface SearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenConversation: (id: string) => void;
  onAskBaco: (text: string) => void;
}

export function SearchModal({
  isOpen,
  onClose,
  onOpenConversation,
  onAskBaco,
}: SearchModalProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const versionRef = useRef(0);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ConversationSummary[]>([]);
  const [saved, setSaved] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  // Load saved once when modal opens; reset state when it closes
  useEffect(() => {
    if (!isOpen) {
      setQuery("");
      setResults([]);
      setError(false);
      setLoading(false);
      versionRef.current = 0;
      return;
    }
    fetchSavedConversations()
      .then((list) => setSaved(list))
      .catch(() => setSaved([]));
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [isOpen]);

  // Debounced search with version guard against stale responses
  useEffect(() => {
    if (!isOpen) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = query.trim();
    if (!trimmed) {
      ++versionRef.current; // invalidate any in-flight request
      setResults([]);
      setError(false);
      setLoading(false);
      return;
    }

    setLoading(true);
    const version = ++versionRef.current;

    debounceRef.current = setTimeout(async () => {
      try {
        const list = await searchConversations(trimmed);
        if (versionRef.current !== version) return;
        setResults(list);
        setError(false);
      } catch {
        if (versionRef.current !== version) return;
        setError(true);
      } finally {
        if (versionRef.current === version) setLoading(false);
      }
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, isOpen]);

  // Escape to close
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleSelect = useCallback(
    (id: string) => {
      onOpenConversation(id);
      onClose();
    },
    [onOpenConversation, onClose]
  );

  if (!isOpen) return null;

  // Filter saved client-side by query
  const trimmed = query.trim().toLowerCase();
  const filteredSaved = trimmed
    ? saved.filter(
        (c) => c.title && c.title.toLowerCase().includes(trimmed)
      )
    : [];

  // Deduplicate: remove from search results any that appear in saved
  const savedIds = new Set(filteredSaved.map((c) => c.id));
  const conversationsOnly = results
    .filter((c) => c.title && !savedIds.has(c.id));

  const hasQuery = trimmed.length > 0;
  const hasResults = conversationsOnly.length > 0 || filteredSaved.length > 0;

  return (
    <>
      <div className="fixed inset-0 z-[60] bg-black/40" onClick={onClose} />
      <div className="fixed inset-x-0 top-[15%] z-[61] mx-auto w-full max-w-lg px-4">
        <div className="bg-wine-bg border border-wine-border rounded-xl shadow-xl overflow-hidden">
          {/* Input */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-wine-border">
            <Search
              size={18}
              strokeWidth={1.5}
              className="text-wine-muted flex-shrink-0"
            />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar conversas..."
              className="flex-1 bg-transparent text-wine-text text-sm placeholder-wine-muted outline-none"
            />
            <kbd className="hidden sm:inline-flex text-xs text-wine-muted bg-wine-surface px-1.5 py-0.5 rounded">
              Esc
            </kbd>
          </div>

          {/* Body */}
          <div className="max-h-72 overflow-y-auto">
            {!hasQuery ? (
              <div className="px-4 py-8 text-center">
                <p className="text-sm text-wine-muted">
                  Digite para buscar em suas conversas.
                </p>
              </div>
            ) : loading ? (
              <div className="px-4 py-6 text-center">
                <div className="w-5 h-5 border-2 border-wine-accent border-t-transparent rounded-full animate-spin mx-auto" />
              </div>
            ) : error ? (
              <div className="px-4 py-6 text-center">
                <p className="text-sm text-wine-muted">
                  Erro ao buscar. Tente novamente.
                </p>
              </div>
            ) : !hasResults ? (
              <div className="px-4 py-8 text-center">
                <p className="text-sm text-wine-muted">
                  Nenhum resultado encontrado.
                </p>
              </div>
            ) : (
              <div className="py-1">
                {filteredSaved.length > 0 && (
                  <div>
                    <p className="px-4 pt-2 pb-1 text-xs font-medium text-wine-muted uppercase tracking-wider">
                      Salvos
                    </p>
                    {filteredSaved.map((conv) => (
                      <ResultItem
                        key={conv.id}
                        conv={conv}
                        saved
                        onClick={() => handleSelect(conv.id)}
                      />
                    ))}
                  </div>
                )}
                {conversationsOnly.length > 0 && (
                  <div>
                    <p className="px-4 pt-2 pb-1 text-xs font-medium text-wine-muted uppercase tracking-wider">
                      Conversas
                    </p>
                    {conversationsOnly.map((conv) => (
                      <ResultItem
                        key={conv.id}
                        conv={conv}
                        onClick={() => handleSelect(conv.id)}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* CTA: ask Baco */}
          {hasQuery && !loading && !error && (
            <div className="border-t border-wine-border px-4 py-3">
              <button
                onClick={() => onAskBaco(query.trim())}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-wine-accent hover:bg-wine-surface transition-colors"
              >
                <MessageCircle size={16} strokeWidth={1.5} className="flex-shrink-0" />
                <span className="truncate">
                  Perguntar ao Baco sobre &ldquo;{query.trim().slice(0, 60)}&rdquo;
                </span>
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function ResultItem({
  conv,
  saved,
  onClick,
}: {
  conv: ConversationSummary;
  saved?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-2 flex items-center gap-2 hover:bg-wine-surface transition-colors"
    >
      <span className="flex-1 text-sm text-wine-text truncate">
        {conv.title}
      </span>
      {saved && (
        <Heart
          size={14}
          strokeWidth={1.5}
          className="text-wine-accent flex-shrink-0"
          fill="currentColor"
        />
      )}
    </button>
  );
}
