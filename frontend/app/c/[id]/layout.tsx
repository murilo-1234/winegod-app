import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

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
  const t = await getTranslations("share.meta");

  try {
    const res = await fetch(`${API_URL}/api/share/${id}`, {
      cache: "no-store",
    });

    if (!res.ok) {
      return {
        title: t("notFoundTitle"),
        description: t("notFoundDescription"),
      };
    }

    const data: ShareData = await res.json();
    const wineNames = data.wines
      .slice(0, 3)
      .map((w) => w.nome)
      .join(", ");
    const description =
      data.context || t("descriptionFromWines", { names: wineNames });

    return {
      title: t("titleSuffix", { title: data.title }),
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
      title: t("fallbackTitle"),
      description: t("fallbackDescription"),
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
