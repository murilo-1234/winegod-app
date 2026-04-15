interface LegalPageProps {
  title: string;
  description?: string;
  lastUpdated?: string;
  children: React.ReactNode;
}

export function LegalPage({
  title,
  description,
  lastUpdated,
  children,
}: LegalPageProps) {
  return (
    <div className="min-h-dvh bg-wine-bg flex flex-col">
      <header className="flex-shrink-0 border-b border-wine-border">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center">
          <a href="/" aria-label="Voltar ao chat">
            <img src="/logo.png" alt="winegod.ai" className="h-12 w-auto" />
          </a>
        </div>
      </header>

      <main className="flex-1 max-w-3xl mx-auto w-full px-4 py-8">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-2">
          {title}
        </h1>
        {description && (
          <p className="text-wine-muted text-sm mb-4">{description}</p>
        )}
        {lastUpdated && (
          <p className="text-wine-muted text-xs mb-6">
            Última atualização: {lastUpdated}
          </p>
        )}

        <div
          className={[
            "text-wine-text text-sm leading-relaxed",
            "[&_h2]:font-display [&_h2]:text-lg [&_h2]:font-bold [&_h2]:text-wine-text [&_h2]:mt-8 [&_h2]:mb-3",
            "[&_h3]:font-semibold [&_h3]:text-base [&_h3]:mt-6 [&_h3]:mb-2",
            "[&_p]:mb-3",
            "[&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-5",
            "[&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-5",
            "[&_li]:mb-1",
            "[&_a]:text-wine-accent [&_a]:underline",
            "[&_strong]:font-semibold",
          ].join(" ")}
        >
          {children}
        </div>
      </main>

      <footer className="flex-shrink-0 border-t border-wine-border">
        <div className="max-w-3xl mx-auto px-4 py-6 text-center text-wine-muted text-xs">
          <a href="/" className="text-wine-accent hover:underline">
            winegod.ai
          </a>
          {" — Wine Intelligence, Powered by Gods"}
        </div>
      </footer>
    </div>
  );
}
