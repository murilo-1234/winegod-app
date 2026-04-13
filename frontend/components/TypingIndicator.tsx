"use client";

export function TypingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="bg-wine-surface px-4 py-3 rounded-2xl rounded-bl-md">
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
          <span className="text-wine-muted text-sm">
            Baco está pensando...
          </span>
        </div>
      </div>
    </div>
  );
}
