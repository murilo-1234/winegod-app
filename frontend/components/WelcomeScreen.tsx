"use client";

import { Camera, Wine, ClipboardList, Store, Scale, FileText } from "lucide-react";

const CARDS = [
  {
    icon: Camera,
    title: "Foto de rótulo",
    prompt: "Tire uma foto de um rótulo de vinho e me envie — eu identifico, avalio e digo onde comprar.",
  },
  {
    icon: Wine,
    title: "Recomendação",
    prompt: "Me indica um vinho tinto até R$80 com boa nota",
  },
  {
    icon: ClipboardList,
    title: "Cardápio",
    prompt: "Analise este cardápio de vinhos e me diga qual é o melhor custo-benefício",
  },
  {
    icon: Store,
    title: "Prateleira",
    prompt: "Vou te mandar uma foto da prateleira de vinhos do mercado — me diz quais valem a pena",
  },
  {
    icon: Scale,
    title: "Comparar",
    prompt: "Compare dois vinhos pra mim",
  },
  {
    icon: FileText,
    title: "Lista de vinhos",
    prompt: "Vou te enviar uma lista de vinhos — analise todos e me diga quais são os melhores",
  },
];

interface WelcomeScreenProps {
  onSuggestionClick: (text: string) => void;
  userName?: string;
  chatInputSlot?: React.ReactNode;
}

export function WelcomeScreen({ onSuggestionClick, userName, chatInputSlot }: WelcomeScreenProps) {
  const topRow = CARDS.slice(0, 4);
  const bottomRow = CARDS.slice(4, 6);

  const greeting = userName
    ? `Saudações, ${userName}!`
    : "Saudações, alma curiosa!";

  return (
    <div className="flex-1 flex flex-col">
      {/* Greeting - centered */}
      <div className="flex-1 flex flex-col items-center justify-center px-6">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-3">
          {greeting}
        </h1>
        <p className="text-wine-muted text-sm leading-relaxed text-center max-w-md">
          Sou Baco — deus do vinho e seu sommelier pessoal. Me pergunte sobre
          qualquer vinho, mande uma foto de rótulo, ou me diga quanto quer gastar
          que eu resolvo.
        </p>
      </div>

      {/* Chat input slot - between greeting and cards */}
      {chatInputSlot && (
        <div className="px-4 pb-3">
          {chatInputSlot}
        </div>
      )}

      {/* Cards - bottom, below input (style Gemini) */}
      <div className="px-4 pb-3">
        <div className="w-full max-w-xl mx-auto">
          {/* Top row: 4 cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {topRow.map((card) => (
              <button
                key={card.title}
                type="button"
                onClick={() => onSuggestionClick(card.prompt)}
                className="flex flex-col items-center gap-1 px-3 py-1.5 rounded-xl bg-wine-surface border border-wine-border hover:border-wine-accent hover:bg-wine-accent/5 transition-colors"
              >
                <card.icon size={22} className="text-wine-accent" />
                <span className="text-xs font-medium text-wine-text text-center">
                  {card.title}
                </span>
              </button>
            ))}
          </div>

          {/* Bottom row: 2 cards centered */}
          <div className="grid grid-cols-2 gap-3 mt-3 max-w-[calc(50%+6px)] mx-auto">
            {bottomRow.map((card) => (
              <button
                key={card.title}
                type="button"
                onClick={() => onSuggestionClick(card.prompt)}
                className="flex flex-col items-center gap-1 px-3 py-1.5 rounded-xl bg-wine-surface border border-wine-border hover:border-wine-accent hover:bg-wine-accent/5 transition-colors"
              >
                <card.icon size={22} className="text-wine-accent" />
                <span className="text-xs font-medium text-wine-text text-center">
                  {card.title}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
