interface ScoreBadgeProps {
  nota: number;
  tipo: "verified" | "estimated";
}

export function ScoreBadge({ nota, tipo }: ScoreBadgeProps) {
  const isEstimated = tipo === "estimated";

  return (
    <span
      className={`text-lg font-bold ${
        isEstimated ? "text-wine-text/60" : "text-wine-text"
      }`}
    >
      {isEstimated ? "~" : ""}
      {nota.toFixed(2)}{" "}
      <span className="text-[#FFD700]">&#9733;</span>
    </span>
  );
}
