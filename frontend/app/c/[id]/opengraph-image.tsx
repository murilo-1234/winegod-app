import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "winegod.ai - Recomendação de vinhos";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface ShareWine {
  nome: string;
  pais_nome: string;
  display_note: number | null;
}

interface ShareData {
  title: string;
  wines: ShareWine[];
}

export default async function OGImage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let title = "Recomendação de vinhos";
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
                  {wine.pais_nome}
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
          Recomendado por Baco, o sommelier IA
        </div>
      </div>
    ),
    { ...size }
  );
}
