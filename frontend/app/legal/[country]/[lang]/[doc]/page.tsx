import type { Metadata } from "next";
import { readFileSync } from "fs";
import path from "path";
import { redirect, notFound } from "next/navigation";
import matter from "gray-matter";
import ReactMarkdown from "react-markdown";
import { getTranslations } from "next-intl/server";
import { LegalPage } from "@/components/LegalPage";
import { DeleteAccountSection } from "@/app/data-deletion/DeleteAccountSection";

const ALLOWED_DOCS = ["privacy", "terms", "data-deletion", "cookies"] as const;
type Doc = (typeof ALLOWED_DOCS)[number];

// F7.0 - matriz enxuta Tier 1: apenas 2 celulas publicadas.
// Nesta rodada (F7.5 FIX1) BR/pt-BR NAO publica `cookies` — acesso a
// /legal/BR/pt-BR/cookies cai em fallback para DEFAULT/en-US.
const PUBLISHED_MATRIX: Record<string, Record<string, readonly Doc[]>> = {
  BR: {
    "pt-BR": ["privacy", "terms", "data-deletion"],
  },
  DEFAULT: {
    "en-US": ["privacy", "terms", "data-deletion", "cookies"],
  },
};

const DELETE_PLACEHOLDER = "[[DELETE_ACCOUNT_SECTION]]";

type Frontmatter = {
  title?: string;
  description?: string;
  last_updated?: string;
  version?: string;
  effective_date?: string;
  binding_language?: string | null;
  jurisdiction?: string;
  doc?: string;
};

type LoadedDoc = {
  country: string;
  lang: string;
  doc: Doc;
  data: Frontmatter;
  body: string;
};

function isAllowedDoc(value: string): value is Doc {
  return (ALLOWED_DOCS as readonly string[]).includes(value);
}

function isPublished(country: string, lang: string, doc: Doc): boolean {
  return PUBLISHED_MATRIX[country]?.[lang]?.includes(doc) ?? false;
}

function resolveLegalPath(country: string, lang: string, doc: Doc): string {
  // shared/legal/ vive fora do frontend/. Em npm run build local o cwd e
  // frontend/, entao subimos um nivel.
  return path.join(
    process.cwd(),
    "..",
    "shared",
    "legal",
    country,
    lang,
    `${doc}.md`,
  );
}

function loadDoc(country: string, lang: string, doc: Doc): LoadedDoc | null {
  try {
    const raw = readFileSync(resolveLegalPath(country, lang, doc), "utf-8");
    const parsed = matter(raw);
    return {
      country,
      lang,
      doc,
      data: parsed.data as Frontmatter,
      body: parsed.content,
    };
  } catch {
    return null;
  }
}

// F7.7 - Labels do chrome do legal carregadas de messages/*.json via
// namespace `legal.*`. O locale do chrome e forcado para o `lang` da URL
// (independente do cookie do usuario), de modo que o documento e seu
// chrome fiquem sempre na mesma lingua.
async function loadChromeLabels(lang: string) {
  const t = await getTranslations({ locale: lang, namespace: "legal" });
  return {
    backToChat: t("backToChat"),
    lastUpdatedLabel: t("lastUpdatedLabel"),
    footerTagline: t("footerTagline"),
    renderFallbackBanner: (from: string) => t("fallbackBanner", { from }),
  };
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ country: string; lang: string; doc: string }>;
}): Promise<Metadata> {
  const { country, lang, doc } = await params;
  if (!isAllowedDoc(doc)) {
    return { title: "winegod.ai" };
  }
  const loaded = loadDoc(country, lang, doc);
  if (!loaded) {
    // Quando a combinacao cai em fallback, deixamos o metadata do destino
    // (DEFAULT/en-US) responder via o proprio documento carregado na rota
    // de destino apos redirect. Aqui retornamos um placeholder neutro.
    return { title: "winegod.ai" };
  }
  return {
    title: loaded.data.title
      ? `${loaded.data.title} — winegod.ai`
      : "winegod.ai",
    description: loaded.data.description,
  };
}

// Injeta o componente interativo de exclusao de conta no lugar do
// placeholder `[[DELETE_ACCOUNT_SECTION]]`. Divide o markdown em
// [antes, depois] e renderiza ReactMarkdown em cada metade.
function renderBodyWithDeleteSection(body: string) {
  const idx = body.indexOf(DELETE_PLACEHOLDER);
  if (idx === -1) {
    return <ReactMarkdown>{body}</ReactMarkdown>;
  }
  const before = body.slice(0, idx);
  const after = body.slice(idx + DELETE_PLACEHOLDER.length);
  return (
    <>
      {before.trim() && <ReactMarkdown>{before}</ReactMarkdown>}
      <DeleteAccountSection />
      {after.trim() && <ReactMarkdown>{after}</ReactMarkdown>}
    </>
  );
}

export default async function LegalDocPage({
  params,
  searchParams,
}: {
  params: Promise<{ country: string; lang: string; doc: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { country, lang, doc } = await params;
  if (!isAllowedDoc(doc)) {
    notFound();
  }

  // F7.5 - 302 fallback para combinacoes nao publicadas.
  if (!isPublished(country, lang, doc)) {
    const from = `${country}/${lang}`;
    redirect(
      `/legal/DEFAULT/en-US/${doc}?fallback_from=${encodeURIComponent(from)}`,
    );
  }

  const loaded = loadDoc(country, lang, doc);
  if (!loaded) {
    // Combinacao declarada publicada mas arquivo faltando: 404 real
    // (nao e caso de fallback).
    notFound();
  }

  const sp = await searchParams;
  const fallbackFromRaw = sp.fallback_from;
  const fallbackFrom = Array.isArray(fallbackFromRaw)
    ? fallbackFromRaw[0]
    : fallbackFromRaw;

  const labels = await loadChromeLabels(lang);
  const banner = fallbackFrom ? (
    <div className="rounded-lg border border-wine-border bg-wine-surface px-4 py-3 text-sm text-wine-text">
      {labels.renderFallbackBanner(fallbackFrom)}
    </div>
  ) : null;

  return (
    <LegalPage
      title={loaded.data.title ?? ""}
      description={loaded.data.description}
      lastUpdated={loaded.data.last_updated}
      lastUpdatedLabel={labels.lastUpdatedLabel}
      banner={banner}
      backToChatAriaLabel={labels.backToChat}
      footerTagline={labels.footerTagline}
    >
      {renderBodyWithDeleteSection(loaded.body)}
    </LegalPage>
  );
}
