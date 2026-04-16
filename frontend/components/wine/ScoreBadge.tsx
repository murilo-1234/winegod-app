interface ScoreBadgeProps {
  nota: number | null;
  tipo: "verified" | "estimated" | "contextual" | null;
}

export function ScoreBadge({ nota, tipo }: ScoreBadgeProps) {
  if (nota == null) return null;

  const isApproximate = tipo === "estimated" || tipo === "contextual";

  return (
    <span
      className={`text-lg font-bold ${
        isApproximate ? "text-wine-text/60" : "text-wine-text"
      }`}
    >
      {isApproximate ? "~" : ""}
      {nota.toFixed(2)}{" "}
      <span className="text-[#FFD700]">&#9733;</span>
    </span>
  );
}
