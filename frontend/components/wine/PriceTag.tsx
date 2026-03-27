interface PriceTagProps {
  precoMin: number | null;
  precoMax: number | null;
  moeda: string;
}

function formatCurrency(value: number, moeda: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: moeda,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${moeda} ${value}`;
  }
}

export function PriceTag({ precoMin, precoMax, moeda }: PriceTagProps) {
  if (precoMin == null && precoMax == null) {
    return <span className="text-sm text-wine-muted">Preco indisponivel</span>;
  }

  const min = precoMin ?? precoMax!;
  const max = precoMax ?? precoMin!;

  return (
    <span className="text-sm font-semibold text-wine-accent">
      {min === max
        ? formatCurrency(min, moeda)
        : `${formatCurrency(min, moeda)} - ${formatCurrency(max, moeda)}`}
    </span>
  );
}
