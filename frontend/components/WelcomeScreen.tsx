"use client";

const SUGGESTIONS = [
  "Qual vinho combina com pizza?",
  "Me indica um tinto ate R$80",
  "O que e terroir?",
  "Cabernet ou Merlot?",
];

interface WelcomeScreenProps {
  onSuggestionClick: (text: string) => void;
}

export function WelcomeScreen({ onSuggestionClick }: WelcomeScreenProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6">
      <div className="text-center mb-10">
        <h1 className="text-3xl font-bold text-wine-text tracking-tight mb-2">
          winegod.ai
        </h1>
        <p className="text-wine-muted text-sm">
          Seu sommelier pessoal com milhares de anos de experiencia
        </p>
      </div>

      <div className="w-full max-w-sm grid grid-cols-2 gap-3">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onSuggestionClick(suggestion)}
            className="w-full text-left px-4 py-3 rounded-xl bg-wine-surface border border-wine-border text-wine-text text-sm hover:border-wine-accent transition-colors"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}
