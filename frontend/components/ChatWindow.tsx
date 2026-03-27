"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "@/components/MessageBubble";
import { TypingIndicator } from "@/components/TypingIndicator";
import type { Message } from "@/lib/types";

interface ChatWindowProps {
  messages: Message[];
  isTyping: boolean;
  onSend?: (text: string) => void;
}

export function ChatWindow({ messages, isTyping, onSend }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <div className="flex flex-col">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} onSend={onSend} />
        ))}
        {isTyping && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
