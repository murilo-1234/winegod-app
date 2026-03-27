interface QuickButtonsProps {
  onAction: (text: string) => void;
}

const QUICK_ACTIONS = [
  { label: "Comparar com outro", message: "Compara esse com outro vinho" },
  { label: "Ver similares", message: "Me mostra vinhos similares" },
  { label: "Mais barato", message: "Tem algo mais barato na mesma qualidade?" },
  { label: "Onde comprar", message: "Onde compro esse vinho?" },
];

export function QuickButtons({ onAction }: QuickButtonsProps) {
  return (
    <div className="flex gap-2 overflow-x-auto py-2">
      {QUICK_ACTIONS.map((action) => (
        <button
          key={action.label}
          onClick={() => onAction(action.message)}
          className="flex-shrink-0 px-3 py-1.5 text-xs rounded-full border border-wine-accent text-wine-accent hover:bg-wine-accent/10 transition-colors whitespace-nowrap"
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}
