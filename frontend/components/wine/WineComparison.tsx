import { WineCard } from "./WineCard";
import type { WineData } from "@/lib/types";

interface WineComparisonProps {
  wines: WineData[];
  onAction?: (text: string) => void;
}

export function WineComparison({ wines, onAction }: WineComparisonProps) {
  const bestScore = Math.max(...wines.map((w) => w.score));

  return (
    <div className="flex flex-col sm:flex-row gap-3 overflow-x-auto">
      {wines.map((wine) => (
        <WineCard
          key={wine.id}
          wine={wine}
          onAction={onAction}
          highlight={wine.score === bestScore && wines.length > 1}
        />
      ))}
    </div>
  );
}
