"use client";

import { useState, useRef, useCallback, type KeyboardEvent } from "react";

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    if (!text.trim() || disabled) return;
    onSend(text);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [text, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setText(e.target.value);
      const el = e.target;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
    },
    []
  );

  return (
    <div className="flex-shrink-0 border-t border-wine-border bg-wine-bg px-4 py-3">
      <div className="flex items-end gap-2">
        <button
          type="button"
          disabled
          className="flex-shrink-0 w-10 h-10 rounded-full bg-wine-input border border-wine-border flex items-center justify-center text-wine-muted opacity-50 cursor-not-allowed"
          title="Em breve"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </button>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="Pergunte ao Baco sobre vinhos..."
          rows={1}
          className="flex-1 bg-wine-input border border-wine-border rounded-xl px-4 py-2.5 text-sm text-wine-text placeholder-wine-muted resize-none focus:outline-none focus:border-wine-accent transition-colors disabled:opacity-50"
        />

        <button
          type="button"
          onClick={handleSend}
          disabled={disabled || !text.trim()}
          className="flex-shrink-0 w-10 h-10 rounded-full bg-wine-accent flex items-center justify-center text-wine-text transition-opacity hover:opacity-80 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  );
}
