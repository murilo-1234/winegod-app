import { ScoreBadge } from "./ScoreBadge";
import { TermBadges } from "./TermBadges";
import { PriceTag } from "./PriceTag";
import type { WineData } from "@/lib/types";

interface WineCardProps {
  wine: WineData;
  onAction?: (text: string) => void;
  highlight?: boolean;
}

export function WineCard({ wine, onAction, highlight }: WineCardProps) {
  return (
    <div
      className={`rounded-xl border p-4 w-full max-w-[400px] hover:border-wine-accent transition-colors ${
        highlight ? "border-wine-accent" : "border-wine-border"
      } bg-wine-surface`}
    >
      <div className="flex gap-3">
        <div className="flex-shrink-0 w-14 h-14 rounded-lg bg-wine-input flex items-center justify-center overflow-hidden">
          {wine.imagem_url ? (
            <img
              src={wine.imagem_url}
              alt={wine.nome}
              className="w-full h-full object-cover"
            />
          ) : (
            <svg
              className="w-7 h-7 text-wine-muted"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M8 2h8v6a4 4 0 1 1-8 0V2z" />
              <path d="M12 12v6" />
              <path d="M8 18h8" />
            </svg>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-bold text-wine-text truncate">
            {wine.nome}
          </h3>
          <p className="text-xs text-wine-muted truncate">{wine.produtor}</p>
          <p className="text-xs text-wine-muted">
            {wine.regiao}, {wine.pais}
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-3 flex-wrap">
        <ScoreBadge nota={wine.nota} tipo={wine.nota_tipo} />
        <TermBadges termos={wine.termos} />
      </div>

      <div className="mt-3 flex items-center justify-between">
        <PriceTag
          precoMin={wine.preco_min}
          precoMax={wine.preco_max}
          moeda={wine.moeda}
        />
        <span className="text-xs text-wine-muted">
          {wine.total_fontes} {wine.total_fontes === 1 ? "loja" : "lojas"}
        </span>
      </div>

      {onAction && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => onAction(`Onde compro ${wine.nome}?`)}
            className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-wine-accent text-wine-accent hover:bg-wine-accent/10 transition-colors"
          >
            Onde comprar
          </button>
          <button
            onClick={() =>
              onAction(`Me mostra vinhos similares a ${wine.nome}`)
            }
            className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-wine-accent text-wine-accent hover:bg-wine-accent/10 transition-colors"
          >
            Similares
          </button>
        </div>
      )}
    </div>
  );
}
