"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { ChatWindow } from "@/components/ChatWindow";
import { ChatInput } from "@/components/ChatInput";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { LoginButton } from "@/components/auth/LoginButton";
import { UserMenu } from "@/components/auth/UserMenu";
import { CreditsBanner } from "@/components/auth/CreditsBanner";
import { sendMessageStream } from "@/lib/api";
import { getUser, logout as doLogout, isLoggedIn as checkLoggedIn } from "@/lib/auth";
import type { UserData } from "@/lib/auth";
import type { Message } from "@/lib/types";

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const doneCalledRef = useRef(false);
  const [user, setUser] = useState<UserData | null>(null);
  const [creditsUsed, setCreditsUsed] = useState(0);
  const [creditsLimit, setCreditsLimit] = useState(5);
  const [creditsExhausted, setCreditsExhausted] = useState<"guest_limit" | "daily_limit" | null>(null);

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

  const handleLogout = useCallback(async () => {
    await doLogout();
    setUser(null);
    setCreditsUsed(0);
    setCreditsLimit(5);
    setCreditsExhausted(null);
  }, []);

  const handleSend = useCallback(
    async (text: string, image?: string) => {
      if ((!text.trim() && !image) || isTyping) return;

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: text.trim() || "O que voce pode me dizer sobre este vinho?",
        timestamp: new Date(),
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
        text.trim() || "O que voce pode me dizer sobre este vinho?",
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
        image
      );
    },
    [isTyping]
  );

  return (
    <main className="flex flex-col h-dvh pb-16 max-w-3xl mx-auto">
      <header className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-wine-border">
        <div className="flex items-center gap-2">
          <img src="/icon.png" alt="WineGod" className="w-14 h-14" />
          <span className="text-wine-text text-sm font-medium tracking-wide">
            winegod.ai
          </span>
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
        <WelcomeScreen onSuggestionClick={handleSend} />
      ) : (
        <ChatWindow messages={messages} isTyping={isTyping} onSend={handleSend} />
      )}
      {creditsExhausted && (
        <CreditsBanner isLoggedIn={!!user} reason={creditsExhausted} />
      )}
      <ChatInput onSend={handleSend} disabled={isTyping || !!creditsExhausted} />
    </main>
  );
}
