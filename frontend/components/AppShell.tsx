"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { SearchModal } from "./SearchModal";
import { LoginButton } from "./auth/LoginButton";
import { UserMenu } from "./auth/UserMenu";
import {
  getUser,
  getCredits,
  logout as doLogout,
  isLoggedIn as checkLoggedIn,
} from "@/lib/auth";
import { getSessionId, resetSessionId } from "@/lib/api";
import type { UserData } from "@/lib/auth";

interface AppShellProps {
  children: React.ReactNode;
  user?: UserData | null;
  creditsUsed?: number;
  creditsLimit?: number;
  onLogout?: () => void;
  onNewChat?: () => void;
  onOpenConversation?: (id: string) => void;
  onAskBaco?: (text: string) => void;
  activeConversationId?: string | null;
  activeConversationSaved?: boolean;
  onToggleSaved?: () => void;
  toggleSavedPending?: boolean;
  toggleSavedError?: boolean;
  conversationsRefreshKey?: number;
}

export function AppShell({
  children,
  user: userProp,
  creditsUsed: creditsUsedProp,
  creditsLimit: creditsLimitProp,
  onLogout,
  onNewChat,
  onOpenConversation,
  onAskBaco,
  activeConversationId,
  conversationsRefreshKey,
}: AppShellProps) {
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  // Ctrl+K to open search — skip inside input/textarea/contentEditable
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        const tag = (e.target as HTMLElement)?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return;
        if ((e.target as HTMLElement)?.isContentEditable) return;
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Self-managed auth — used when parent doesn't pass user prop
  const managed = userProp === undefined;
  const [shellUser, setShellUser] = useState<UserData | null>(null);
  const [shellCreditsUsed, setShellCreditsUsed] = useState(0);
  const [shellCreditsLimit, setShellCreditsLimit] = useState(0);

  useEffect(() => {
    if (!managed) return;
    async function init() {
      if (checkLoggedIn()) {
        const data = await getUser();
        if (data) {
          setShellUser(data.user);
          setShellCreditsUsed(data.credits.used);
          setShellCreditsLimit(data.credits.limit);
          return;
        }
      }
      const credits = await getCredits(getSessionId());
      if (credits) {
        setShellCreditsUsed(credits.used);
        setShellCreditsLimit(credits.limit);
      }
    }
    init();
  }, [managed]);

  const handleShellLogout = useCallback(async () => {
    await doLogout();
    setShellUser(null);
    resetSessionId();
    const credits = await getCredits(getSessionId());
    if (credits) {
      setShellCreditsUsed(credits.used);
      setShellCreditsLimit(credits.limit);
    }
  }, []);

  // Resolve active values: explicit props override self-managed state
  const user = managed ? shellUser : (userProp ?? null);
  const creditsUsed = managed ? shellCreditsUsed : (creditsUsedProp ?? 0);
  const creditsLimit = managed ? shellCreditsLimit : (creditsLimitProp ?? 0);
  const activeOnLogout = managed ? handleShellLogout : onLogout;

  return (
    <>
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => {
          if (onNewChat) {
            onNewChat();
          } else {
            router.push("/");
          }
          setSidebarOpen(false);
        }}
        onSearch={() => setSearchOpen(true)}
        onExpandSidebar={() => setSidebarOpen(true)}
        userName={user?.name}
        creditsUsed={creditsUsed}
        creditsLimit={creditsLimit}
        isLoggedIn={!!user}
        onOpenConversation={onOpenConversation}
        activeConversationId={activeConversationId}
        conversationsRefreshKey={conversationsRefreshKey}
      />
      <div className="md:pl-12 flex flex-col h-dvh">
        <header className="flex-shrink-0 border-b border-wine-border">
          <div className="flex items-center justify-between px-4 py-2 max-w-3xl mx-auto">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSidebarOpen(true)}
                className="md:hidden p-2 rounded-lg hover:bg-wine-surface transition-colors text-wine-muted"
                aria-label="Abrir menu"
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="3" y1="8" x2="21" y2="8" />
                  <line x1="3" y1="16" x2="21" y2="16" />
                </svg>
              </button>
              <Link
                href="/"
                onClick={() => onNewChat?.()}
                aria-label="Voltar ao início"
              >
                <img
                  src="/logo.png"
                  alt="winegod.ai"
                  className="h-14 w-auto"
                />
              </Link>
            </div>
            <div className="flex items-center gap-1">
              {user ? (
                <UserMenu
                  user={user}
                  creditsUsed={creditsUsed}
                  creditsLimit={creditsLimit}
                  onLogout={activeOnLogout ?? (() => {})}
                />
              ) : (
                <>
                  {creditsLimit > 0 && (
                    <span className="text-wine-muted text-xs px-2 hidden sm:block">
                      {Math.max(0, creditsLimit - creditsUsed)}/{creditsLimit}
                    </span>
                  )}
                  <LoginButton compact />
                </>
              )}
            </div>
          </div>
        </header>
        <div className="flex-1 min-h-0">{children}</div>
      </div>
      <SearchModal
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        onOpenConversation={(id) => {
          if (onOpenConversation) {
            onOpenConversation(id);
          } else {
            router.push(`/?conv=${id}`);
          }
          setSearchOpen(false);
        }}
        onAskBaco={(text) => {
          if (onAskBaco) {
            onAskBaco(text);
          } else {
            router.push(`/?ask=${encodeURIComponent(text)}`);
          }
          setSearchOpen(false);
        }}
      />
    </>
  );
}
