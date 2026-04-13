"use client";

import { useState } from "react";
import { Camera, Wine, ClipboardList, Store, Scale, FileText } from "lucide-react";

// ── Saudações por período do dia (fuso do usuário) ──

const GREETINGS: Record<string, { anonymous: string[]; named: string[] }> = {
  madrugada: {
    anonymous: [
      "Ainda acordado? Baco também não dorme.",
      "A madrugada é dos curiosos — e dos bons vinhos.",
      "As melhores escolhas se fazem quando o mundo dorme.",
      "Noite longa? Eu conheço o vinho certo pra isso.",
      "O mundo dorme, mas o vinho nunca descansa.",
      "Hora perfeita pra uma taça e uma boa conversa.",
      "Poucos sabem, mas os deuses fazem suas melhores escolhas de madrugada.",
    ],
    named: [
      "Ainda de pé, {name}? Baco também não dorme.",
      "A madrugada é sua, {name}. E os vinhos também.",
      "{name}, insônia ou paixão? De qualquer forma, estou aqui.",
      "O silêncio da noite combina com um bom vinho, {name}.",
      "{name}, só nós dois e 1.7 milhão de vinhos. Vamos?",
      "Boa hora pra uma descoberta, {name}. O mundo tá quieto.",
      "{name}! Madrugada é hora de segredos — e de bons rótulos.",
    ],
  },
  manha: {
    anonymous: [
      "Bom dia! Café primeiro, vinho depois — ou não.",
      "Manhã fresca. Hora perfeita pra planejar o jantar.",
      "O dia é jovem e cheio de vinhos por descobrir.",
      "Bom dia! Já sabe o que vai beber hoje?",
      "Sol nascendo, ideias brotando. Me conta o que procura!",
      "Manhã de decisões. A mais importante: qual vinho escolher.",
      "Bom dia! Um deus do vinho a seu dispor — pode perguntar.",
    ],
    named: [
      "Bom dia, {name}! Vamos encontrar algo especial hoje?",
      "Manhã, {name}! Café ou vinho — por que não os dois?",
      "{name}, o dia mal começou e já penso em vinhos. Você também?",
      "Bom dia, {name}! Pronto pra uma nova descoberta?",
      "{name}! Dia novo, vinhos novos. O que vai ser hoje?",
      "Bom dia, {name}! O Olimpo acordou cedo pra te ajudar.",
      "Manhã, {name}! Me diz o que procura que eu resolvo.",
    ],
  },
  tarde: {
    anonymous: [
      "Boa tarde! O almoço merece um bom acompanhamento.",
      "Tarde perfeita pra descobrir um vinho novo.",
      "O sol ainda está alto — e a vontade de vinho também.",
      "Boa tarde! Me conta: o que você tá buscando?",
      "Meio do dia, meio da jornada. Vamos achar seu vinho?",
      "Boa tarde! Nada como um bom vinho pra alegrar o resto do dia.",
      "A tarde é curta, mas dá tempo de achar o vinho perfeito.",
    ],
    named: [
      "Boa tarde, {name}! Posso ajudar na escolha de hoje?",
      "{name}, tarde perfeita pra descobrir algo novo.",
      "Boa tarde, {name}! Que tipo de vinho combina com o seu dia?",
      "{name}! A tarde pede um bom cálice. Posso ajudar?",
      "Boa tarde, {name}! Já pensou no vinho de hoje?",
      "{name}, o dia tá passando — vamos garantir o vinho da noite?",
      "Boa tarde, {name}! Um deus do vinho à sua disposição.",
    ],
  },
  noite: {
    anonymous: [
      "Boa noite! Hora perfeita pra um bom cálice.",
      "A noite chegou — e com ela, a hora do vinho.",
      "Boa noite! O jantar merece um vinho à altura.",
      "A noite é pra relaxar. Me diz o que procura.",
      "As estrelas saíram. E os melhores vinhos também.",
      "Boa noite! Fim do dia, começo da diversão. O que vai ser?",
      "Noite é hora de celebrar — mesmo que seja só uma terça.",
    ],
    named: [
      "Boa noite, {name}! Hora de escolher o vinho do jantar?",
      "{name}, a noite caiu. Vamos encontrar algo especial?",
      "Boa noite, {name}! Relaxa — o sommelier cuida de tudo.",
      "{name}! Noite perfeita pra um bom vinho. O que prefere?",
      "Boa noite, {name}! O dia foi longo, mas o vinho compensa.",
      "{name}, a noite é sua. Me conta o que combina com ela.",
      "Boa noite, {name}! Taça na mão e me diz o que procura.",
    ],
  },
};

function getTimeGreeting(userName?: string): string {
  const hour = new Date().getHours();
  let period: string;
  if (hour >= 0 && hour < 6) period = "madrugada";
  else if (hour < 12) period = "manha";
  else if (hour < 18) period = "tarde";
  else period = "noite";

  const pool = userName ? GREETINGS[period].named : GREETINGS[period].anonymous;
  const idx = Math.floor(Math.random() * pool.length);
  const phrase = pool[idx];
  return userName ? phrase.replace("{name}", userName) : phrase;
}

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

  const [greeting] = useState(() => getTimeGreeting(userName));

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
