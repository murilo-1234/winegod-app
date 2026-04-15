"use client";

import { useState, useCallback, useRef, useEffect, useLayoutEffect } from "react";
import { useRouter } from "next/navigation";
import { Heart } from "lucide-react";
import { ChatWindow } from "@/components/ChatWindow";
import { ChatInput } from "@/components/ChatInput";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { CreditsBanner } from "@/components/auth/CreditsBanner";
import { AppShell } from "@/components/AppShell";
import { sendMessageStream, getSessionId, setSessionId, resetSessionId } from "@/lib/api";
import {
  fetchConversation,
  migrateGuestConversation,
  updateConversationSaved,
} from "@/lib/conversations";
import type { MediaPayload } from "@/lib/api";
import { getUser, getCredits, logout as doLogout, isLoggedIn as checkLoggedIn } from "@/lib/auth";
import type { UserData } from "@/lib/auth";
import type { Message } from "@/lib/types";

const MESSAGES_KEY = "winegod_messages";
const CONV_ID_KEY = "winegod_conversation_id";

const useIsoLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

function generateMigrationTitle(
  messages: { role: string; content: string }[]
): string {
  const firstUser = messages.find((m) => m.role === "user")?.content || "";
  let text = firstUser.trim();
  for (const pfx of ["[Foto] ", "[Video] ", "[PDF] ", "[Foto]", "[Video]", "[PDF]"]) {
    if (text.startsWith(pfx)) {
      text = text.slice(pfx.length).trim();
      break;
    }
  }
  if (text.length > 3) return text.slice(0, 100);
  const firstAsst = messages.find((m) => m.role === "assistant")?.content || "";
  if (firstAsst.trim().length > 3) return firstAsst.trim().slice(0, 100);
  return "Nova conversa";
}

interface ChatHomeProps {
  initialConversationId?: string;
}

export function ChatHome({ initialConversationId }: ChatHomeProps) {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const doneCalledRef = useRef(false);
  const [user, setUser] = useState<UserData | null>(null);
  const [creditsUsed, setCreditsUsed] = useState(0);
  const [creditsLimit, setCreditsLimit] = useState(0);
  const [creditsExhausted, setCreditsExhausted] = useState<"guest_limit" | "daily_limit" | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(
    initialConversationId ?? null
  );
  const [openingConversation, setOpeningConversation] = useState(
    !!initialConversationId
  );
  const [mounted, setMounted] = useState(false);

  useIsoLayoutEffect(() => {
    setMounted(true);
    if (initialConversationId) {
      // /chat/<id> route — body stays as spinner until init effect fetches
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const legacyConv = params.get("conv");
    if (legacyConv) {
      // Backwards compatibility: redirect /?conv=<id> to /chat/<id>
      router.replace(`/chat/${legacyConv}`);
      setOpeningConversation(true);
      return;
    }
    const savedConvId = sessionStorage.getItem(CONV_ID_KEY);
    if (savedConvId) {
      // Same-tab refresh restore — promote to /chat/<id> URL
      router.replace(`/chat/${savedConvId}`);
      setConversationId(savedConvId);
      setOpeningConversation(true);
      return;
    }
    try {
      const raw = sessionStorage.getItem(MESSAGES_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        setMessages(
          parsed.map((m: Message) => ({ ...m, timestamp: new Date(m.timestamp) }))
        );
      }
    } catch {}
  }, [initialConversationId, router]);

  const [convRefreshKey, setConvRefreshKey] = useState(0);
  const [pendingAsk, setPendingAsk] = useState<string | null>(null);
  const [conversationSaved, setConversationSaved] = useState(false);
  const [togglePending, setTogglePending] = useState(false);
  const [toggleError, setToggleError] = useState(false);
  const [toggleNotice, setToggleNotice] = useState<"saved" | "removed" | null>(null);
  const toggleRequestRef = useRef(0);

  const refreshCredits = useCallback(async () => {
    const hadToken = checkLoggedIn();
    const data = await getCredits(getSessionId());
    if (data) {
      setCreditsUsed(data.used);
      setCreditsLimit(data.limit);
      return;
    }
    if (hadToken && !checkLoggedIn()) {
      setUser(null);
      const guest = await getCredits(getSessionId());
      if (guest) {
        setCreditsUsed(guest.used);
        setCreditsLimit(guest.limit);
      }
    }
  }, []);

  useEffect(() => {
    async function init() {
      const params = new URLSearchParams(window.location.search);
      const askParam = params.get("ask");

      if (askParam) {
        window.history.replaceState({}, "", "/");
        setMessages([]);
        setConversationId(null);
        if (checkLoggedIn()) {
          resetSessionId();
        }
        sessionStorage.removeItem(MESSAGES_KEY);
        localStorage.removeItem(MESSAGES_KEY);
        setIsTyping(false);
        setCreditsExhausted(null);
        setPendingAsk(askParam);
      }

      if (checkLoggedIn()) {
        const data = await getUser();
        if (data) {
          setUser(data.user);
          setCreditsUsed(data.credits.used);
          setCreditsLimit(data.credits.limit);

          if (askParam) return;

          // /chat/<id> route — load that conversation directly
          if (initialConversationId) {
            setSessionId(initialConversationId);
            const conv = await fetchConversation(initialConversationId);
            if (conv && conv.messages.length) {
              setMessages(
                conv.messages.map((m, i) => ({
                  id: `${initialConversationId}-${i}`,
                  role: m.role as "user" | "assistant",
                  content: m.content,
                  timestamp: new Date(conv.updated_at || Date.now()),
                }))
              );
              setConversationSaved(!!conv.is_saved);
            } else {
              // Conversation not found or empty — drop back to home
              setConversationId(null);
              router.replace("/");
            }
            setOpeningConversation(false);
            return;
          }

          const legacyConv = params.get("conv");
          if (legacyConv) {
            // Already redirected by useIsoLayoutEffect; nothing to fetch here
            return;
          }

          const savedConvId = sessionStorage.getItem(CONV_ID_KEY);
          if (savedConvId) {
            // Already redirected by useIsoLayoutEffect; nothing to fetch here
            return;
          }

          // No active conversation — migrate guest draft if present
          const draftRaw = sessionStorage.getItem(MESSAGES_KEY);
          if (draftRaw) {
            try {
              const parsed = JSON.parse(draftRaw);
              if (Array.isArray(parsed) && parsed.length > 0) {
                const cleanMsgs = parsed
                  .filter(
                    (m: Record<string, unknown>) => m.role && m.content
                  )
                  .map((m: Record<string, unknown>) => ({
                    role: m.role as string,
                    content: m.content as string,
                  }));
                if (cleanMsgs.length > 0) {
                  const sid = getSessionId();
                  const title = generateMigrationTitle(cleanMsgs);
                  const ok = await migrateGuestConversation(
                    sid,
                    title,
                    cleanMsgs
                  );
                  if (ok) {
                    setConversationId(sid);
                    setConvRefreshKey((k) => k + 1);
                    router.replace(`/chat/${sid}`);
                  }
                }
              }
            } catch {
              // Migration failed — draft stays local
            }
          }
          return;
        }
        // Token invalid/expired — getUser() already removed it, fall through to guest
      }
      // Guest path
      if (initialConversationId) {
        // Guest landing on /chat/<id> directly — bounce to home
        router.replace("/");
        return;
      }
      setOpeningConversation(false);
      refreshCredits();
    }
    init();
  }, [refreshCredits, initialConversationId, router]);

  // Persist guest draft to sessionStorage only
  useEffect(() => {
    if (conversationId) return;
    if (messages.length === 0) {
      sessionStorage.removeItem(MESSAGES_KEY);
      return;
    }
    sessionStorage.setItem(MESSAGES_KEY, JSON.stringify(messages));
  }, [messages, conversationId]);

  // Persist conversationId across refresh
  useEffect(() => {
    if (conversationId) {
      sessionStorage.setItem(CONV_ID_KEY, conversationId);
      sessionStorage.removeItem(MESSAGES_KEY);
      localStorage.removeItem(MESSAGES_KEY);
    } else {
      sessionStorage.removeItem(CONV_ID_KEY);
    }
  }, [conversationId]);

  useEffect(() => {
    toggleRequestRef.current++;
    setTogglePending(false);
    setToggleError(false);
    setToggleNotice(null);
  }, [conversationId]);

  useEffect(() => {
    if (!toggleNotice) return;
    const timeout = window.setTimeout(() => setToggleNotice(null), 2200);
    return () => window.clearTimeout(timeout);
  }, [toggleNotice]);

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setConversationSaved(false);
    setOpeningConversation(false);
    if (user) {
      resetSessionId();
    }
    // Clear storage synchronously — router.push("/") would otherwise mount
    // the home before the [conversationId] effect runs, and the home would
    // read the stale CONV_ID_KEY and redirect right back to /chat/<id>.
    sessionStorage.removeItem(MESSAGES_KEY);
    sessionStorage.removeItem(CONV_ID_KEY);
    localStorage.removeItem(MESSAGES_KEY);
    setIsTyping(false);
    setCreditsExhausted(null);
    if (window.location.pathname !== "/") {
      router.push("/");
    }
  }, [user, router]);

  const handleAskBaco = useCallback(
    (text: string) => {
      handleNewChat();
      setPendingAsk(text);
    },
    [handleNewChat]
  );

  const handleOpenConversation = useCallback(
    (id: string) => {
      // Always navigate to /chat/<id> so the URL is the source of truth
      router.push(`/chat/${id}`);
    },
    [router]
  );

  const handleToggleSaved = useCallback(async () => {
    if (!conversationId || togglePending) return;

    const targetId = conversationId;
    const next = !conversationSaved;
    const version = ++toggleRequestRef.current;

    setConversationSaved(next);
    setTogglePending(true);
    setToggleError(false);

    const ok = await updateConversationSaved(targetId, next);

    if (toggleRequestRef.current !== version) return;

    if (ok) {
      setTogglePending(false);
      setToggleNotice(next ? "saved" : "removed");
      setConvRefreshKey((k) => k + 1);
    } else {
      setConversationSaved(!next);
      setTogglePending(false);
      setToggleError(true);
    }
  }, [conversationId, conversationSaved, togglePending]);

  const handleLogout = useCallback(async () => {
    await doLogout();
    setUser(null);
    setMessages([]);
    setConversationId(null);
    setCreditsExhausted(null);
    resetSessionId();
    sessionStorage.removeItem(MESSAGES_KEY);
    sessionStorage.removeItem(CONV_ID_KEY);
    localStorage.removeItem(MESSAGES_KEY);
    refreshCredits();
    if (window.location.pathname !== "/") {
      router.push("/");
    }
  }, [refreshCredits, router]);

  const handleSend = useCallback(
    async (text: string, media?: MediaPayload) => {
      if ((!text.trim() && !media) || isTyping) return;

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: text.trim() || "O que você pode me dizer sobre este vinho?",
        timestamp: new Date(),
        imagePreviews: media?.previews,
      };

      const bacoId = crypto.randomUUID();
      const bacoMessage: Message = {
        id: bacoId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMessage, bacoMessage]);
      setIsTyping(true);
      doneCalledRef.current = false;

      await sendMessageStream(
        text.trim() || "O que você pode me dizer sobre este vinho?",
        {
          onChunk: (chunk) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === bacoId
                  ? { ...msg, content: msg.content + chunk }
                  : msg
              )
            );
          },
          onDone: () => {
            if (doneCalledRef.current) return;
            doneCalledRef.current = true;
            setIsTyping(false);
            (async () => {
              await refreshCredits();
              let promotedId: string | null = null;
              setConversationId((prev) => {
                if (prev) {
                  promotedId = prev;
                  return prev;
                }
                if (!checkLoggedIn()) return null;
                const sid = getSessionId();
                promotedId = sid;
                return sid;
              });
              setConvRefreshKey((k) => k + 1);
              if (promotedId && window.location.pathname === "/") {
                router.replace(`/chat/${promotedId}`);
              }
            })();
          },
          onCreditsExhausted: (reason) => {
            setCreditsExhausted(reason);
            setMessages((prev) => prev.filter((msg) => msg.id !== bacoId));
            setIsTyping(false);
            refreshCredits();
          },
          onError: (error) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === bacoId
                  ? {
                      ...msg,
                      content:
                        msg.content ||
                        `Ops, algo deu errado: ${error}. Tente novamente!`,
                    }
                  : msg
              )
            );
            setIsTyping(false);
          },
        },
        media
      );
    },
    [isTyping, refreshCredits, router]
  );

  useEffect(() => {
    if (!pendingAsk || isTyping) return;
    const text = pendingAsk;
    setPendingAsk(null);
    handleSend(text);
  }, [pendingAsk, isTyping, handleSend]);

  return (
    <AppShell
      user={user}
      creditsUsed={creditsUsed}
      creditsLimit={creditsLimit}
      onLogout={handleLogout}
      onNewChat={handleNewChat}
      onOpenConversation={handleOpenConversation}
      onAskBaco={handleAskBaco}
      activeConversationId={conversationId}
      conversationsRefreshKey={convRefreshKey}
    >
      <main className="relative flex flex-col h-full pb-16 max-w-3xl mx-auto w-full">
        {user && conversationId && (
          <div className="pointer-events-none absolute inset-y-0 right-0 z-10 flex items-center pr-3 md:pr-5">
            <div className="pointer-events-auto flex items-center gap-2">
              {(togglePending || toggleError || toggleNotice || conversationSaved) && (
                <div
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium shadow-sm backdrop-blur ${
                    toggleError
                      ? "border-red-200 bg-red-50 text-red-600"
                      : "border-wine-border bg-white/95 text-wine-text"
                  }`}
                  aria-live="polite"
                >
                  {toggleError
                    ? "Erro ao salvar"
                    : togglePending
                    ? "Salvando..."
                    : toggleNotice === "removed"
                    ? "Removida dos favoritos"
                    : "Salva nos favoritos"}
                </div>
              )}
              <button
                type="button"
                onClick={handleToggleSaved}
                disabled={togglePending}
                className={`flex h-12 w-12 items-center justify-center rounded-full border bg-white/95 shadow-sm backdrop-blur transition-colors md:h-14 md:w-14 ${
                  togglePending
                    ? "cursor-not-allowed border-wine-border opacity-50"
                    : toggleError
                    ? "border-red-300 hover:bg-red-50"
                    : "border-wine-border hover:border-wine-accent hover:bg-wine-surface"
                }`}
                aria-label={
                  togglePending
                    ? "Salvando..."
                    : conversationSaved
                    ? "Remover dos favoritos"
                    : "Salvar nos favoritos"
                }
                title={
                  toggleError
                    ? "Erro ao salvar. Clique para tentar novamente."
                    : togglePending
                    ? "Salvando..."
                    : conversationSaved
                    ? "Remover dos favoritos"
                    : "Salvar nos favoritos"
                }
              >
                <Heart
                  size={32}
                  strokeWidth={1.8}
                  className={
                    toggleError
                      ? "text-red-500"
                      : conversationSaved
                      ? "text-wine-accent"
                      : "text-wine-text"
                  }
                  fill={conversationSaved ? "currentColor" : "none"}
                />
              </button>
            </div>
          </div>
        )}
        {!mounted || openingConversation ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-wine-accent border-t-transparent rounded-full animate-spin" />
          </div>
        ) : messages.length === 0 && !isTyping ? (
          <WelcomeScreen
            onSuggestionClick={handleSend}
            userName={user?.name}
            chatInputSlot={<ChatInput onSend={handleSend} disabled={isTyping || !!creditsExhausted} />}
          />
        ) : (
          <>
            <ChatWindow messages={messages} isTyping={isTyping} onSend={handleSend} />
            {creditsExhausted && (
              <CreditsBanner isLoggedIn={!!user} reason={creditsExhausted} />
            )}
            <ChatInput onSend={handleSend} disabled={isTyping || !!creditsExhausted} />
          </>
        )}
      </main>
    </AppShell>
  );
}
