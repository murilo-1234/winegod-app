interface TermBadgesProps {
  termos: string[];
}

export function TermBadges({ termos }: TermBadgesProps) {
  if (!termos || termos.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {termos.map((termo) => (
        <span
          key={termo}
          className="px-2 py-0.5 text-xs rounded-full bg-[#2A2A4E] text-[#C0C0C0]"
        >
          {termo}
        </span>
      ))}
    </div>
  );
}
