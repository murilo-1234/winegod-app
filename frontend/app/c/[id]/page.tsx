import { WineCard } from "@/components/wine/WineCard";
import type { WineData } from "@/lib/types";
import Link from "next/link";
import { notFound } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface ShareWine {
  id: number;
  nome: string;
  produtor: string;
  safra: string;
  tipo: string;
  pais_nome: string;
  regiao: string;
  vivino_rating: number;
  nota_wcf: number;
  winegod_score: number;
  preco_min: number | null;
  preco_max: number | null;
  moeda: string;
  display_note: number | null;
  display_note_type: "verified" | "estimated" | "contextual" | null;
  display_score: number | null;
  display_score_available: boolean;
  public_ratings_bucket: string | null;
}

interface ShareData {
  share_id: string;
  title: string;
  context: string;
  wines: ShareWine[];
  created_at: string;
}

function toWineData(w: ShareWine): WineData {
  return {
    id: w.id,
    nome: w.nome,
    produtor: w.produtor || "",
    safra: w.safra || "",
    tipo: w.tipo || "",
    pais: w.pais_nome || "",
    regiao: w.regiao || "",
    uvas: [],
    nota: w.display_note ?? null,
    nota_tipo: w.display_note_type ?? null,
    nota_bucket: w.public_ratings_bucket ?? null,
    score: w.display_score ?? 0,
    termos: [],
    preco_min: w.preco_min,
    preco_max: w.preco_max,
    moeda: w.moeda || "BRL",
    imagem_url: null,
    total_fontes: 0,
  };
}

async function getShareData(id: string): Promise<ShareData | null> {
  try {
    const res = await fetch(`${API_URL}/api/share/${id}`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function SharePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const data = await getShareData(id);

  if (!data) {
    notFound();
  }

  return (
    <main className="min-h-dvh bg-wine-bg text-wine-text">
      {/* Header */}
      <header className="border-b border-wine-border px-4 py-3">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <Link href="/" className="text-lg font-bold text-wine-text">
            winegod<span className="text-wine-accent">.ai</span>
          </Link>
          <Link
            href="/"
            className="px-4 py-2 text-sm rounded-lg border border-wine-accent text-wine-accent hover:bg-wine-accent/10 transition-colors"
          >
            Abrir no Chat
          </Link>
        </div>
      </header>

      {/* Content */}
      <div className="max-w-2xl mx-auto px-4 py-8">
        {/* Title & Context */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-wine-text mb-2">{data.title}</h1>
          {data.context && (
            <p className="text-wine-muted text-sm">{data.context}</p>
          )}
        </div>

        {/* Wine Cards */}
        <div className="flex flex-col gap-4 items-center">
          {data.wines.map((wine) => (
            <WineCard key={wine.id} wine={toWineData(wine)} />
          ))}
        </div>

        {data.wines.length === 0 && (
          <p className="text-center text-wine-muted py-12">
            Nenhum vinho encontrado neste compartilhamento.
          </p>
        )}
      </div>

      {/* Footer */}
      <footer className="border-t border-wine-border px-4 py-6 mt-12">
        <div className="max-w-2xl mx-auto text-center">
          <p className="text-wine-muted text-sm">
            Descubra mais vinhos em{" "}
            <Link href="/" className="text-wine-accent hover:underline">
              chat.winegod.ai
            </Link>
          </p>
        </div>
      </footer>
    </main>
  );
}
