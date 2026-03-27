"use client";

export function TypingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="flex items-start gap-2">
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-wine-accent flex items-center justify-center text-sm mt-1">
          B
        </div>
        <div className="bg-wine-surface px-4 py-3 rounded-2xl rounded-bl-md">
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
            <span className="text-wine-muted text-sm">
              Baco esta pensando...
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
