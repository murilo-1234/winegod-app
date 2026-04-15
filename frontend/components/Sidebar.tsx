"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, Search, Menu, Heart, User, CreditCard, CircleHelp } from "lucide-react";
import { fetchConversations, type ConversationSummary } from "@/lib/conversations";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onSearch?: () => void;
  onExpandSidebar?: () => void;
  userName?: string;
  creditsUsed?: number;
  creditsLimit?: number;
  isLoggedIn: boolean;
  onOpenConversation?: (id: string) => void;
  activeConversationId?: string | null;
  conversationsRefreshKey?: number;
}

const ICON_SIZE = 20;
const STROKE = 1.5;

function IconBtn({
  icon,
  tooltip,
  onClick,
}: {
  icon: React.ReactNode;
  tooltip: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-10 h-10 flex items-center justify-center rounded-lg hover:bg-wine-surface text-[#6b6b6b] hover:text-wine-text transition-colors"
      title={tooltip}
    >
      {icon}
    </button>
  );
}

function SidebarLink({
  icon,
  label,
  shortcut,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  shortcut?: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-wine-surface text-sm text-wine-text transition-colors"
    >
      <span className="text-[#6b6b6b] flex-shrink-0">{icon}</span>
      <span className="flex-1 text-left">{label}</span>
      {shortcut && (
        <span className="text-xs text-wine-muted bg-wine-surface px-1.5 py-0.5 rounded">
          {shortcut}
        </span>
      )}
    </button>
  );
}

function IconLink({
  icon,
  tooltip,
  href,
}: {
  icon: React.ReactNode;
  tooltip: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="w-10 h-10 flex items-center justify-center rounded-lg hover:bg-wine-surface text-[#6b6b6b] hover:text-wine-text transition-colors"
      title={tooltip}
    >
      {icon}
    </Link>
  );
}

function SidebarNavLink({
  icon,
  label,
  href,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  href: string;
  onClick?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-wine-surface text-sm text-wine-text transition-colors"
    >
      <span className="text-[#6b6b6b] flex-shrink-0">{icon}</span>
      <span className="flex-1 text-left">{label}</span>
    </Link>
  );
}

export function Sidebar({
  isOpen,
  onClose,
  onNewChat,
  onSearch,
  onExpandSidebar,
  creditsUsed,
  creditsLimit,
  isLoggedIn,
  onOpenConversation,
  activeConversationId,
  conversationsRefreshKey,
}: SidebarProps) {
  const router = useRouter();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [convLoading, setConvLoading] = useState(false);
  const [convError, setConvError] = useState(false);

  const loadConversations = useCallback(async () => {
    if (!isLoggedIn) {
      setConversations([]);
      setConvError(false);
      return;
    }
    setConvLoading(true);
    setConvError(false);
    try {
      const list = await fetchConversations();
      setConversations(list);
    } catch {
      setConvError(true);
    } finally {
      setConvLoading(false);
    }
  }, [isLoggedIn]);

  useEffect(() => {
    loadConversations();
  }, [loadConversations, conversationsRefreshKey]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
    }
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  const creditsLabel =
    isLoggedIn && creditsUsed != null && creditsLimit != null
      ? `Plano & créditos (${creditsUsed}/${creditsLimit})`
      : "Plano & créditos";

  return (
    <>
      {/* ── Collapsed icon strip (desktop only, always visible) ── */}
      <nav
        className={`hidden md:flex fixed top-0 left-0 h-full w-12 bg-wine-bg border-r border-wine-border flex-col items-center pt-3 pb-3 gap-0.5 ${
          isOpen ? "z-30" : "z-[60]"
        }`}
      >
        <IconBtn
          icon={<Menu size={ICON_SIZE} strokeWidth={STROKE} />}
          tooltip="Abrir menu"
          onClick={onExpandSidebar}
        />

        <div className="w-6 border-t border-wine-border/50 my-1.5" />

        <IconBtn
          icon={<Plus size={ICON_SIZE} strokeWidth={STROKE} />}
          tooltip="Novo chat"
          onClick={onNewChat}
        />
        <IconBtn
          icon={<Search size={ICON_SIZE} strokeWidth={STROKE} />}
          tooltip="Buscar"
          onClick={onSearch}
        />

        <div className="w-6 border-t border-wine-border/50 my-1.5" />

        <IconLink
          icon={<Heart size={ICON_SIZE} strokeWidth={STROKE} />}
          tooltip="Favoritos"
          href="/favoritos"
        />
        <IconLink
          icon={<User size={ICON_SIZE} strokeWidth={STROKE} />}
          tooltip="Minha conta"
          href="/conta"
        />
        <IconLink
          icon={<CreditCard size={ICON_SIZE} strokeWidth={STROKE} />}
          tooltip={creditsLabel}
          href="/plano"
        />

        <div className="flex-1" />

        <IconLink
          icon={<CircleHelp size={ICON_SIZE} strokeWidth={STROKE} />}
          tooltip="Ajuda"
          href="/ajuda"
        />
      </nav>

      {/* ── Overlay (expanded) ── */}
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity duration-200 ${
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={onClose}
      />

      {/* ── Expanded sidebar ── */}
      <aside
        className={`fixed top-0 left-0 h-full z-50 w-64 bg-wine-bg border-r border-wine-border flex flex-col transition-transform duration-200 ${
          isOpen
            ? "translate-x-0 visible pointer-events-auto"
            : "-translate-x-full invisible pointer-events-none"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-3">
          <span className="font-display text-lg font-bold text-wine-text">
            winegod.ai
          </span>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-wine-surface transition-colors text-wine-muted"
            aria-label="Fechar menu"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Main menu */}
        <div className="px-2 py-1">
          <SidebarLink
            icon={<Plus size={ICON_SIZE} strokeWidth={STROKE} />}
            label="Novo chat"
            onClick={() => {
              onNewChat();
              onClose();
            }}
          />
          <SidebarLink
            icon={<Search size={ICON_SIZE} strokeWidth={STROKE} />}
            label="Buscar"
            shortcut="Ctrl+K"
            onClick={() => {
              onSearch?.();
              onClose();
            }}
          />
        </div>

        <div className="mx-3 border-t border-wine-border/50" />

        <div className="px-2 py-1">
          <SidebarNavLink
            icon={<Heart size={ICON_SIZE} strokeWidth={STROKE} />}
            label="Favoritos"
            href="/favoritos"
            onClick={onClose}
          />
          <SidebarNavLink
            icon={<User size={ICON_SIZE} strokeWidth={STROKE} />}
            label="Minha conta"
            href="/conta"
            onClick={onClose}
          />
          <SidebarNavLink
            icon={<CreditCard size={ICON_SIZE} strokeWidth={STROKE} />}
            label={creditsLabel}
            href="/plano"
            onClick={onClose}
          />
        </div>

        <div className="mx-3 border-t border-wine-border/50" />

        {/* History */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          <p className="text-xs font-medium text-wine-muted uppercase tracking-wider px-3 mb-2">
            Histórico
          </p>
          {convLoading ? (
            <div className="px-3 space-y-2">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-8 bg-wine-surface/50 rounded animate-pulse"
                />
              ))}
            </div>
          ) : convError ? (
            <div className="px-3">
              <p className="text-sm text-wine-muted">
                Erro ao carregar histórico.
              </p>
              <button
                onClick={loadConversations}
                className="text-sm text-wine-accent hover:underline mt-1"
              >
                Tentar novamente
              </button>
            </div>
          ) : !isLoggedIn ? (
            <p className="text-sm text-wine-muted px-3">
              Entre com sua conta para ver seu histórico.
            </p>
          ) : conversations.filter((c) => c.title).length === 0 ? (
            <p className="text-sm text-wine-muted px-3">
              Suas conversas aparecerão aqui.
            </p>
          ) : (
            <div className="space-y-0.5">
              {conversations
                .filter((c) => c.title)
                .map((conv) => (
                  <button
                    key={conv.id}
                    onClick={() => {
                      if (onOpenConversation) {
                        onOpenConversation(conv.id);
                      } else {
                        router.push(`/chat/${conv.id}`);
                      }
                      onClose();
                    }}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors truncate ${
                      activeConversationId === conv.id
                        ? "bg-wine-surface text-wine-text"
                        : "text-wine-muted hover:bg-wine-surface hover:text-wine-text"
                    }`}
                    title={conv.title || "Conversa sem título"}
                  >
                    {conv.title || "Conversa sem título"}
                  </button>
                ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-2 pb-3 border-t border-wine-border pt-2">
          <SidebarNavLink
            icon={<CircleHelp size={ICON_SIZE} strokeWidth={STROKE} />}
            label="Ajuda"
            href="/ajuda"
            onClick={onClose}
          />
        </div>
      </aside>
    </>
  );
}
