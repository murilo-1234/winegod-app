import { ImageResponse } from "next/og";
import { cookies, headers } from "next/headers";

export const runtime = "edge";
// Static `alt` must be a string at module level; kept in US-facing English to
// remove the pt-BR literal. Image body copy (title fallback + footer) is
// resolved per-request from cookie/geo in the default export below.
export const alt = "winegod.ai — Wine recommendation";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface ShareWine {
  nome: string;
  pais_display?: string;
  pais_nome: string;
  display_note: number | null;
}

interface ShareData {
  title: string;
  wines: ShareWine[];
}

// Inline copy mirrored from messages/{pt-BR,en-US}.json > share.og.
// Kept local to this edge route to avoid bundling the full messages file.
// es-419 and fr-FR follow the fallback chain to en-US (US-facing default).
type OgLocale = "pt-BR" | "en-US";

const OG_STRINGS: Record<OgLocale, { fallbackTitle: string; footer: string }> = {
  "pt-BR": {
    fallbackTitle: "Recomendação de vinhos",
    footer: "Recomendado por Baco, o sommelier IA",
  },
  "en-US": {
    fallbackTitle: "Wine recommendation",
    footer: "Recommended by Baco, the AI sommelier",
  },
};

async function resolveOgLocale(): Promise<OgLocale> {
  try {
    const cookieStore = await cookies();
    const cookie = cookieStore.get("wg_locale_choice")?.value;
    if (cookie === "pt-BR") return "pt-BR";
    if (cookie === "en-US" || cookie === "es-419" || cookie === "fr-FR") {
      return "en-US";
    }

    const headerStore = await headers();
    const country = (
      headerStore.get("x-vercel-ip-country") ??
      headerStore.get("X-Vercel-IP-Country") ??
      ""
    ).toUpperCase();
    if (country === "BR") return "pt-BR";
    if (country) return "en-US";

    return "pt-BR";
  } catch {
    return "pt-BR";
  }
}

export default async function OGImage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const locale = await resolveOgLocale();
  const copy = OG_STRINGS[locale];

  let title = copy.fallbackTitle;
  let wines: ShareWine[] = [];

  try {
    const res = await fetch(`${API_URL}/api/share/${id}`, {
      cache: "no-store",
    });
    if (res.ok) {
      const data: ShareData = await res.json();
      title = data.title || title;
      wines = data.wines.slice(0, 3);
    }
  } catch {
    // fallback to defaults
  }

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          backgroundColor: "#8B1A4A",
          padding: "60px",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        {/* Logo */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            marginBottom: "40px",
          }}
        >
          <span
            style={{
              fontSize: "36px",
              fontWeight: 700,
              color: "#FFFFFF",
            }}
          >
            winegod
          </span>
          <span
            style={{
              fontSize: "36px",
              fontWeight: 700,
              color: "#8B1A4A",
            }}
          >
            .ai
          </span>
        </div>

        {/* Title */}
        <div
          style={{
            fontSize: "48px",
            fontWeight: 700,
            color: "#FFFFFF",
            marginBottom: "40px",
            lineHeight: 1.2,
          }}
        >
          {title}
        </div>

        {/* Wine List */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "16px",
            flex: 1,
          }}
        >
          {wines.map((wine, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "16px",
              }}
            >
              <div
                style={{
                  width: "40px",
                  height: "40px",
                  borderRadius: "8px",
                  backgroundColor: "rgba(255,255,255,0.15)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#FFFFFF",
                  fontSize: "20px",
                  fontWeight: 700,
                }}
              >
                {i + 1}
              </div>
              <div style={{ display: "flex", flexDirection: "column" }}>
                <span
                  style={{
                    fontSize: "24px",
                    color: "#E0E0E0",
                    fontWeight: 600,
                  }}
                >
                  {wine.nome}
                </span>
                <span style={{ fontSize: "16px", color: "#888888" }}>
                  {wine.pais_display || wine.pais_nome}
                  {wine.display_note != null &&
                    ` — ${wine.display_note.toFixed(1)}/5`}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div
          style={{
            fontSize: "18px",
            color: "#888888",
            marginTop: "auto",
          }}
        >
          {copy.footer}
        </div>
      </div>
    ),
    { ...size }
  );
}
