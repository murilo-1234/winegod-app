"use client";

import { useState, useCallback, useRef } from "react";
import { ChatWindow } from "@/components/ChatWindow";
import { ChatInput } from "@/components/ChatInput";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { sendMessageStream } from "@/lib/api";
import type { Message } from "@/lib/types";

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const doneCalledRef = useRef(false);

  const handleSend = useCallback(
    async (text: string) => {
      if (!text.trim() || isTyping) return;

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: text.trim(),
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

      await sendMessageStream(text.trim(), {
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
      });
    },
    [isTyping]
  );

  return (
    <main className="flex flex-col h-dvh max-w-3xl mx-auto">
      {messages.length === 0 && !isTyping ? (
        <WelcomeScreen onSuggestionClick={handleSend} />
      ) : (
        <ChatWindow messages={messages} isTyping={isTyping} />
      )}
      <ChatInput onSend={handleSend} disabled={isTyping} />
    </main>
  );
}
