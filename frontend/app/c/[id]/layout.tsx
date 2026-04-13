import type { Metadata } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface ShareData {
  share_id: string;
  title: string;
  context: string;
  wines: { nome: string }[];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;

  try {
    const res = await fetch(`${API_URL}/api/share/${id}`, {
      cache: "no-store",
    });

    if (!res.ok) {
      return {
        title: "Compartilhamento não encontrado - winegod.ai",
        description: "Este link de compartilhamento não existe ou expirou.",
      };
    }

    const data: ShareData = await res.json();
    const wineNames = data.wines
      .slice(0, 3)
      .map((w) => w.nome)
      .join(", ");
    const description = data.context || `Vinhos: ${wineNames}`;

    return {
      title: `${data.title} - winegod.ai`,
      description,
      openGraph: {
        title: data.title,
        description,
        url: `https://chat.winegod.ai/c/${id}`,
        siteName: "winegod.ai",
        type: "website",
      },
      twitter: {
        card: "summary_large_image",
        title: data.title,
        description,
      },
    };
  } catch {
    return {
      title: "winegod.ai - Seu sommelier pessoal",
      description: "Converse com Baco, seu sommelier pessoal.",
    };
  }
}

export default function ShareLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
