"use client";

import ReactMarkdown from "react-markdown";
import type { Message } from "@/lib/types";

function formatTime(date: Date): string {
  return date.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`flex items-start gap-2 max-w-[85%] ${
          isUser ? "flex-row-reverse" : "flex-row"
        }`}
      >
        {!isUser && (
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-wine-accent flex items-center justify-center text-sm mt-1">
            B
          </div>
        )}

        <div>
          <div
            className={`px-4 py-3 rounded-2xl ${
              isUser
                ? "bg-wine-user rounded-br-md"
                : "bg-wine-surface rounded-bl-md"
            }`}
          >
            {isUser ? (
              <p className="text-wine-text text-sm leading-relaxed whitespace-pre-wrap">
                {message.content}
              </p>
            ) : (
              <div className="text-wine-text text-sm leading-relaxed prose prose-invert prose-sm max-w-none">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
            )}
          </div>
          <p
            className={`text-[11px] text-wine-muted mt-1 ${
              isUser ? "text-right" : "text-left"
            } px-1`}
          >
            {formatTime(message.timestamp)}
          </p>
        </div>
      </div>
    </div>
  );
}
