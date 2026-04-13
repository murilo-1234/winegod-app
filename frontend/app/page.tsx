"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { ChatWindow } from "@/components/ChatWindow";
import { ChatInput } from "@/components/ChatInput";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { LoginButton } from "@/components/auth/LoginButton";
import { UserMenu } from "@/components/auth/UserMenu";
import { CreditsBanner } from "@/components/auth/CreditsBanner";
import { Sidebar } from "@/components/Sidebar";
import { sendMessageStream } from "@/lib/api";
import type { MediaPayload } from "@/lib/api";
import { getUser, logout as doLogout, isLoggedIn as checkLoggedIn } from "@/lib/auth";
import type { UserData } from "@/lib/auth";
import type { Message } from "@/lib/types";

const MESSAGES_KEY = "winegod_messages";

function loadMessages(): Message[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(MESSAGES_KEY) || sessionStorage.getItem(MESSAGES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length > 0) {
      return parsed.map((m: Message) => ({ ...m, timestamp: new Date(m.timestamp) }));
    }
  } catch {}
  return [];
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>(loadMessages);
  const [isTyping, setIsTyping] = useState(false);
  const doneCalledRef = useRef(false);
  const [user, setUser] = useState<UserData | null>(null);
  const [creditsUsed, setCreditsUsed] = useState(0);
  const [creditsLimit, setCreditsLimit] = useState(5);
  const [creditsExhausted, setCreditsExhausted] = useState<"guest_limit" | "daily_limit" | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (checkLoggedIn()) {
      getUser().then((data) => {
        if (data) {
          setUser(data.user);
          setCreditsUsed(data.credits.used);
          setCreditsLimit(data.credits.limit);
        }
      });
    }
  }, []);

  // Persist messages to storage
  useEffect(() => {
    if (messages.length === 0) {
      sessionStorage.removeItem(MESSAGES_KEY);
      localStorage.removeItem(MESSAGES_KEY);
      return;
    }
    const data = JSON.stringify(messages);
    sessionStorage.setItem(MESSAGES_KEY, data);
    if (user) {
      localStorage.setItem(MESSAGES_KEY, data);
    }
  }, [messages, user]);

  const handleNewChat = useCallback(() => {
    setMessages([]);
    sessionStorage.removeItem(MESSAGES_KEY);
    localStorage.removeItem(MESSAGES_KEY);
    setIsTyping(false);
    setCreditsExhausted(null);
  }, []);

  const handleLogout = useCallback(async () => {
    await doLogout();
    setUser(null);
    setCreditsUsed(0);
    setCreditsLimit(5);
    setCreditsExhausted(null);
  }, []);

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
          },
          onError: (error) => {
            if (error.includes("credits_exhausted") || error.includes("429")) {
              const reason = user ? "daily_limit" : "guest_limit";
              setCreditsExhausted(reason);
            }
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
    [isTyping, user]
  );

  return (
    <>
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={handleNewChat}
        onToggle={() => setSidebarOpen((v) => !v)}
        userName={user?.name}
        creditsUsed={creditsUsed}
        creditsLimit={creditsLimit}
        isLoggedIn={!!user}
      />
      <div className="md:pl-12">
      <main className="flex flex-col h-dvh pb-16 max-w-3xl mx-auto">
        <header className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-wine-border">
          <div className="flex items-center gap-2">
            {/* Hamburger — mobile only (desktop has icon strip) */}
            <button
              onClick={() => setSidebarOpen(true)}
              className="md:hidden p-2 rounded-lg hover:bg-wine-surface transition-colors text-wine-muted"
              aria-label="Abrir menu"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="8" x2="21" y2="8" />
                <line x1="3" y1="16" x2="21" y2="16" />
              </svg>
            </button>
            <button onClick={handleNewChat} className="cursor-pointer" aria-label="Voltar ao início">
              <img src="/logo.png" alt="winegod.ai" className="h-14 w-auto" />
            </button>
          </div>
          {user ? (
            <UserMenu
              user={user}
              creditsUsed={creditsUsed}
              creditsLimit={creditsLimit}
              onLogout={handleLogout}
            />
          ) : (
            <LoginButton compact />
          )}
        </header>

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
      </div>
    </>
  );
}
