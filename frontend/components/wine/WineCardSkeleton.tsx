export function WineCardSkeleton() {
  return (
    <div className="rounded-xl border border-wine-border p-4 w-full max-w-[400px] bg-wine-surface animate-pulse">
      <div className="flex gap-3">
        <div className="flex-shrink-0 w-14 h-14 rounded-lg bg-wine-border" />
        <div className="flex-1 space-y-2 py-1">
          <div className="h-4 bg-wine-border rounded w-3/4" />
          <div className="h-3 bg-wine-border rounded w-1/2" />
          <div className="h-3 bg-wine-border rounded w-2/3" />
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <div className="h-6 bg-wine-border rounded w-16" />
        <div className="h-5 bg-wine-border rounded-full w-20" />
        <div className="h-5 bg-wine-border rounded-full w-16" />
      </div>
      <div className="mt-3 flex items-center justify-between">
        <div className="h-4 bg-wine-border rounded w-20" />
        <div className="h-4 bg-wine-border rounded w-12" />
      </div>
    </div>
  );
}
