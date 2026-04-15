"use client";

import { useState, useCallback, useRef, useEffect } from "react";
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

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const doneCalledRef = useRef(false);
  const [user, setUser] = useState<UserData | null>(null);
  const [creditsUsed, setCreditsUsed] = useState(0);
  const [creditsLimit, setCreditsLimit] = useState(0);
  const [creditsExhausted, setCreditsExhausted] = useState<"guest_limit" | "daily_limit" | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);

  // Client-only hydration of guest draft and active conversationId —
  // reading sessionStorage in useState initializer breaks SSR hydration.
  useEffect(() => {
    const savedConvId = sessionStorage.getItem(CONV_ID_KEY);
    if (savedConvId) {
      setConversationId(savedConvId);
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
  }, []);
  const [convRefreshKey, setConvRefreshKey] = useState(0);
  const [pendingAsk, setPendingAsk] = useState<string | null>(null);
  const [conversationSaved, setConversationSaved] = useState(false);
  const [togglePending, setTogglePending] = useState(false);
  const [toggleError, setToggleError] = useState(false);
  const toggleRequestRef = useRef(0);

  const refreshCredits = useCallback(async () => {
    const hadToken = checkLoggedIn();
    const data = await getCredits(getSessionId());
    if (data) {
      setCreditsUsed(data.used);
      setCreditsLimit(data.limit);
      return;
    }
    // Token was removed by getCredits() on 401 — fall through to guest
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

      // Handle ?ask= first — works for guest, authenticated, and fallback guest
      // Mirrors handleNewChat: always reset messages/conversationId/storage,
      // reset sessionId only if token present (matches guest credit preservation)
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

          // ?ask= took priority — skip conv/restore/migrate
          if (askParam) return;

          const convParam = params.get("conv");
          if (convParam) {
            window.history.replaceState({}, "", "/");
            const conv = await fetchConversation(convParam);
            if (conv && conv.messages.length) {
              setMessages(
                conv.messages.map((m, i) => ({
                  id: `${convParam}-${i}`,
                  role: m.role as "user" | "assistant",
                  content: m.content,
                  timestamp: new Date(conv.updated_at || Date.now()),
                }))
              );
              setConversationId(convParam);
              setSessionId(convParam);
              setConversationSaved(!!conv.is_saved);
            }
          } else {
            const savedConvId = sessionStorage.getItem(CONV_ID_KEY);
            if (savedConvId) {
              // Restore conversation from backend on refresh
              setSessionId(savedConvId);
              const conv = await fetchConversation(savedConvId);
              if (conv && conv.messages.length) {
                setMessages(
                  conv.messages.map((m, i) => ({
                    id: `${savedConvId}-${i}`,
                    role: m.role as "user" | "assistant",
                    content: m.content,
                    timestamp: new Date(conv.updated_at || Date.now()),
                  }))
                );
                setConversationId(savedConvId);
                setConversationSaved(!!conv.is_saved);
              } else {
                setConversationId(null);
              }
            } else {
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
                      }
                    }
                  }
                } catch {
                  // Migration failed — draft stays local
                }
              }
            }
          }
          return;
        }
        // Token invalid/expired — getUser() already removed it, fall through to guest
      }
      refreshCredits();
    }
    init();
  }, [refreshCredits]);

  // Persist guest draft to sessionStorage only —
  // authenticated conversations are persisted by the backend.
  // Never write to localStorage — prevents stale data leaking across sessions.
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
      // Clear draft storage — this conversation is backend-managed
      sessionStorage.removeItem(MESSAGES_KEY);
      localStorage.removeItem(MESSAGES_KEY);
    } else {
      sessionStorage.removeItem(CONV_ID_KEY);
    }
  }, [conversationId]);

  // On conversation change, invalidate any in-flight toggle-saved request
  // and reset UI feedback so the new conversation starts clean
  useEffect(() => {
    toggleRequestRef.current++;
    setTogglePending(false);
    setToggleError(false);
  }, [conversationId]);

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setConversationSaved(false);
    if (user) {
      resetSessionId();
    }
    sessionStorage.removeItem(MESSAGES_KEY);
    localStorage.removeItem(MESSAGES_KEY);
    setIsTyping(false);
    setCreditsExhausted(null);
  }, [user]);

  const handleAskBaco = useCallback(
    (text: string) => {
      handleNewChat();
      setPendingAsk(text);
    },
    [handleNewChat]
  );

  const handleOpenConversation = useCallback(async (id: string) => {
    const conv = await fetchConversation(id);
    if (!conv || !conv.messages.length) return;

    setMessages(
      conv.messages.map((m, i) => ({
        id: `${id}-${i}`,
        role: m.role as "user" | "assistant",
        content: m.content,
        timestamp: new Date(conv.updated_at || Date.now()),
      }))
    );
    setConversationId(id);
    setConversationSaved(!!conv.is_saved);
    setSessionId(id);
    setIsTyping(false);
    setCreditsExhausted(null);
  }, []);

  const handleToggleSaved = useCallback(async () => {
    // Guard: require active conversation, block double-click while pending
    if (!conversationId || togglePending) return;

    const targetId = conversationId;
    const next = !conversationSaved;
    // Monotonic version; conversation change also increments this ref
    const version = ++toggleRequestRef.current;

    setConversationSaved(next); // optimistic
    setTogglePending(true);
    setToggleError(false);

    const ok = await updateConversationSaved(targetId, next);

    // Stale if: a newer toggle fired, or conversation changed (ref was bumped)
    if (toggleRequestRef.current !== version) return;

    if (ok) {
      setTogglePending(false);
      setConvRefreshKey((k) => k + 1);
    } else {
      setConversationSaved(!next); // rollback
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
    localStorage.removeItem(MESSAGES_KEY);
    refreshCredits();
  }, [refreshCredits]);

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
            // Await refreshCredits before promoting conversationId —
            // if token expired mid-session, refreshCredits detects 401
            // and removes the token before we check checkLoggedIn()
            (async () => {
              await refreshCredits();
              setConversationId((prev) => {
                if (prev) return prev;
                if (!checkLoggedIn()) return null;
                return getSessionId();
              });
              setConvRefreshKey((k) => k + 1);
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
    [isTyping, refreshCredits]
  );

  // Process pending "ask Baco" from SearchModal (home page or cross-page)
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
      activeConversationSaved={conversationSaved}
      onToggleSaved={handleToggleSaved}
      toggleSavedPending={togglePending}
      toggleSavedError={toggleError}
      conversationsRefreshKey={convRefreshKey}
    >
      <main className="flex flex-col h-full pb-16 max-w-3xl mx-auto">
        {messages.length === 0 && !isTyping ? (
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
