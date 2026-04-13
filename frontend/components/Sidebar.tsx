"use client";

import { useEffect } from "react";
import { Plus, Search, Heart, User, CreditCard, HelpCircle } from "lucide-react";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onToggle: () => void;
  userName?: string;
  creditsUsed?: number;
  creditsLimit?: number;
  isLoggedIn: boolean;
}

const ICON_SIZE = 18;

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
      className="w-10 h-10 flex items-center justify-center rounded-lg hover:bg-wine-surface text-wine-muted hover:text-wine-text transition-colors"
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
      <span className="text-wine-muted flex-shrink-0">{icon}</span>
      <span className="flex-1 text-left">{label}</span>
      {shortcut && (
        <span className="text-xs text-wine-muted bg-wine-surface px-1.5 py-0.5 rounded">
          {shortcut}
        </span>
      )}
    </button>
  );
}

export function Sidebar({
  isOpen,
  onClose,
  onNewChat,
  onToggle,
  creditsUsed,
  creditsLimit,
  isLoggedIn,
}: SidebarProps) {
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
      <nav className="hidden md:flex fixed top-0 left-0 h-full w-12 bg-wine-bg border-r border-wine-border flex-col items-center pt-3 pb-3 gap-0.5 z-30">
        <IconBtn
          icon={<Plus size={ICON_SIZE} />}
          tooltip="Novo chat"
          onClick={onNewChat}
        />
        <IconBtn
          icon={<Search size={ICON_SIZE} />}
          tooltip="Buscar"
          onClick={onToggle}
        />

        <div className="w-6 border-t border-wine-border my-1.5" />

        <IconBtn
          icon={<Heart size={ICON_SIZE} />}
          tooltip="Meus vinhos favoritos"
          onClick={onToggle}
        />
        <IconBtn
          icon={<User size={ICON_SIZE} />}
          tooltip="Minha conta"
          onClick={onToggle}
        />
        <IconBtn
          icon={<CreditCard size={ICON_SIZE} />}
          tooltip={creditsLabel}
          onClick={onToggle}
        />

        <div className="flex-1" />

        <IconBtn
          icon={<HelpCircle size={ICON_SIZE} />}
          tooltip="Ajuda"
          onClick={onToggle}
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
          isOpen ? "translate-x-0" : "-translate-x-full"
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
            icon={<Plus size={ICON_SIZE} />}
            label="Novo chat"
            onClick={() => {
              onNewChat();
              onClose();
            }}
          />
          <SidebarLink
            icon={<Search size={ICON_SIZE} />}
            label="Buscar"
            shortcut="Ctrl+K"
          />
        </div>

        <div className="mx-3 border-t border-wine-border" />

        <div className="px-2 py-1">
          <SidebarLink
            icon={<Heart size={ICON_SIZE} />}
            label="Meus vinhos favoritos"
          />
          <SidebarLink
            icon={<User size={ICON_SIZE} />}
            label="Minha conta"
          />
          <SidebarLink
            icon={<CreditCard size={ICON_SIZE} />}
            label={creditsLabel}
          />
        </div>

        <div className="mx-3 border-t border-wine-border" />

        {/* History */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          <p className="text-xs font-medium text-wine-muted uppercase tracking-wider px-3 mb-2">
            Histórico
          </p>
          <p className="text-sm text-wine-muted px-3">
            Suas conversas aparecerão aqui.
          </p>
        </div>

        {/* Footer */}
        <div className="px-2 pb-3 border-t border-wine-border pt-2">
          <SidebarLink
            icon={<HelpCircle size={ICON_SIZE} />}
            label="Ajuda"
          />
        </div>
      </aside>
    </>
  );
}
