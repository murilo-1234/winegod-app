"use client";

import ReactMarkdown from "react-markdown";
import { WineCard } from "./wine/WineCard";
import { WineComparison } from "./wine/WineComparison";
import { QuickButtons } from "./wine/QuickButtons";
import { ShareButton } from "./ShareButton";
import type { Message, WineData } from "@/lib/types";

function formatTime(date: Date): string {
  return date.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

type ContentSegment =
  | { type: "text"; content: string }
  | { type: "wine_card"; wine: WineData }
  | { type: "wine_comparison"; wines: WineData[] };

function parseContent(content: string): ContentSegment[] {
  const segments: ContentSegment[] = [];
  const regex =
    /<wine-card>([\s\S]*?)<\/wine-card>|<wine-comparison>([\s\S]*?)<\/wine-comparison>/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      const text = content.slice(lastIndex, match.index).trim();
      if (text) segments.push({ type: "text", content: text });
    }

    try {
      if (match[1] !== undefined) {
        const data = JSON.parse(match[1]);
        segments.push({ type: "wine_card", wine: data.wine ?? data });
      } else if (match[2] !== undefined) {
        const data = JSON.parse(match[2]);
        segments.push({
          type: "wine_comparison",
          wines: data.wines ?? data,
        });
      }
    } catch {
      segments.push({ type: "text", content: match[0] });
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    const text = content.slice(lastIndex).trim();
    if (text) segments.push({ type: "text", content: text });
  }

  return segments;
}

interface MessageBubbleProps {
  message: Message;
  onSend?: (text: string) => void;
}

export function MessageBubble({ message, onSend }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const segments = !isUser ? parseContent(message.content) : [];
  const hasInlineWines = segments.some(
    (s) => s.type === "wine_card" || s.type === "wine_comparison"
  );

  const metaWines = message.wines ?? [];
  const showQuickButtons = (hasInlineWines || metaWines.length > 0) && onSend;

  // Coletar wine_ids para o ShareButton
  const allWineIds: number[] = [];
  for (const seg of segments) {
    if (seg.type === "wine_card" && seg.wine.id) allWineIds.push(seg.wine.id);
    if (seg.type === "wine_comparison") {
      for (const w of seg.wines) { if (w.id) allWineIds.push(w.id); }
    }
  }
  for (const embed of metaWines) {
    if (embed.type === "wine_card" && embed.wine.id) allWineIds.push(embed.wine.id);
    if (embed.type === "wine_comparison") {
      for (const w of embed.wines) { if (w.id) allWineIds.push(w.id); }
    }
  }
  const hasWines = allWineIds.length > 0;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-6`}>
      <div
        className={`flex items-start gap-3 ${
          isUser ? "flex-row-reverse max-w-[75%]" : "flex-row w-full max-w-[85%]"
        }`}
      >
        {!isUser && (
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-wine-accent flex items-center justify-center text-sm mt-1 text-white font-semibold">
            B
          </div>
        )}

        <div className="min-w-0 flex-1">
          <div
            className={
              isUser
                ? "px-4 py-2.5 rounded-2xl bg-wine-user text-wine-text"
                : "py-1"
            }
          >
            {isUser ? (
              <div>
                {message.imagePreviews && message.imagePreviews.length > 0 && (
                  <div className="flex gap-1.5 flex-wrap mb-2">
                    {message.imagePreviews.map((src, i) => (
                      <img
                        key={i}
                        src={src}
                        alt={`Foto ${i + 1}`}
                        className="h-20 w-20 object-cover rounded-lg"
                      />
                    ))}
                  </div>
                )}
                <p className="text-sm leading-relaxed whitespace-pre-wrap">
                  {message.content}
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {segments.map((seg, i) => {
                  if (seg.type === "text") {
                    return (
                      <div
                        key={i}
                        className="text-wine-text text-sm leading-relaxed prose prose-sm max-w-none"
                      >
                        <ReactMarkdown>{seg.content}</ReactMarkdown>
                      </div>
                    );
                  }
                  if (seg.type === "wine_card") {
                    return (
                      <WineCard key={i} wine={seg.wine} onAction={onSend} />
                    );
                  }
                  if (seg.type === "wine_comparison") {
                    return (
                      <WineComparison
                        key={i}
                        wines={seg.wines}
                        onAction={onSend}
                      />
                    );
                  }
                  return null;
                })}

                {metaWines.map((embed, i) =>
                  embed.type === "wine_comparison" ? (
                    <WineComparison
                      key={`meta-${i}`}
                      wines={embed.wines}
                      onAction={onSend}
                    />
                  ) : (
                    <WineCard
                      key={`meta-${i}`}
                      wine={embed.wine}
                      onAction={onSend}
                    />
                  )
                )}
              </div>
            )}
          </div>

          {showQuickButtons && (
            <div className="flex items-center gap-2 flex-wrap mt-1">
              <QuickButtons onAction={onSend!} />
              {hasWines && <ShareButton wine_ids={allWineIds} />}
            </div>
          )}

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
