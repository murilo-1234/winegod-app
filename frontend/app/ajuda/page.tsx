import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AppShell } from "@/components/AppShell";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("help.meta");
  return {
    title: t("title"),
    description: t("description"),
  };
}

/* ── Subcomponentes locais ── */

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <h2 className="font-display text-lg font-bold text-wine-text mt-10 mb-4">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Q({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <h3 className="font-semibold text-wine-text text-sm mb-1">{q}</h3>
      <div className="text-wine-muted text-sm leading-relaxed">{children}</div>
    </div>
  );
}

function Term({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <dt className="font-semibold text-wine-text text-sm">{term}</dt>
      <dd className="text-wine-muted text-sm leading-relaxed ml-0">
        {children}
      </dd>
    </div>
  );
}

const INDEX_ITEMS: { href: string; key: string }[] = [
  { href: "#chat", key: "chat" },
  { href: "#fotos", key: "photos" },
  { href: "#notas", key: "notes" },
  { href: "#creditos", key: "credits" },
  { href: "#compartilhar", key: "share" },
  { href: "#conta", key: "account" },
  { href: "#glossario", key: "glossary" },
  { href: "#contato", key: "contact" },
];

const GLOSSARY_KEYS = [
  "baco",
  "rotulo",
  "safra",
  "terroir",
  "tanino",
  "corpo",
  "acidez",
  "secoDoce",
  "blend",
  "varietal",
  "decantacao",
  "ocr",
  "wineGodScore",
  "notaWCF",
  "credito",
  "produtor",
] as const;

/* ── Página ── */

export default async function AjudaPage() {
  const t = await getTranslations("help");
  const chatExamples = t.raw("sections.chat.q2.examples") as string[];

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-4 py-8 overflow-y-auto h-full">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-1">
          {t("header.title")}
        </h1>
        <p className="text-wine-muted text-sm mb-6">
          {t("header.subtitle")}
        </p>

        {/* ── Índice rápido ── */}
        <nav className="mb-8 text-sm flex flex-wrap gap-x-4 gap-y-1">
          {INDEX_ITEMS.map(({ href, key }) => (
            <a
              key={href}
              href={href}
              className="text-wine-accent hover:underline"
            >
              {t(`index.${key}`)}
            </a>
          ))}
        </nav>

        {/* ── FAQ ── */}

        <Section id="chat" title={t("sections.chat.title")}>
          <Q q={t("sections.chat.q1.q")}>
            <p>{t("sections.chat.q1.a")}</p>
          </Q>
          <Q q={t("sections.chat.q2.q")}>
            <p>{t("sections.chat.q2.intro")}</p>
            <ul className="list-disc pl-5 mt-1 space-y-0.5">
              {chatExamples.map((ex, i) => (
                <li key={i}>{ex}</li>
              ))}
            </ul>
          </Q>
          <Q q={t("sections.chat.q3.q")}>
            <p>{t("sections.chat.q3.a")}</p>
          </Q>
        </Section>

        <Section id="fotos" title={t("sections.photos.title")}>
          <Q q={t("sections.photos.q1.q")}>
            <p>{t("sections.photos.q1.a")}</p>
          </Q>
          <Q q={t("sections.photos.q2.q")}>
            <p>{t("sections.photos.q2.a")}</p>
          </Q>
          <Q q={t("sections.photos.q3.q")}>
            <p>{t("sections.photos.q3.a")}</p>
          </Q>
          <Q q={t("sections.photos.q4.q")}>
            <p>{t("sections.photos.q4.a")}</p>
          </Q>
        </Section>

        <Section id="notas" title={t("sections.notes.title")}>
          <Q q={t("sections.notes.q1.q")}>
            <p>{t("sections.notes.q1.a")}</p>
          </Q>
          <Q q={t("sections.notes.q2.q")}>
            <p>{t("sections.notes.q2.a")}</p>
          </Q>
          <Q q={t("sections.notes.q3.q")}>
            <p>{t("sections.notes.q3.a")}</p>
          </Q>
        </Section>

        <Section id="creditos" title={t("sections.credits.title")}>
          <Q q={t("sections.credits.q1.q")}>
            <p>
              {t.rich("sections.credits.q1.a", {
                b: (chunks) => <strong>{chunks}</strong>,
              })}
            </p>
          </Q>
          <Q q={t("sections.credits.q2.q")}>
            <p>{t("sections.credits.q2.a")}</p>
          </Q>
          <Q q={t("sections.credits.q3.q")}>
            <p>{t("sections.credits.q3.a")}</p>
          </Q>
        </Section>

        <Section id="compartilhar" title={t("sections.share.title")}>
          <Q q={t("sections.share.q1.q")}>
            <p>{t("sections.share.q1.a")}</p>
          </Q>
        </Section>

        <Section id="conta" title={t("sections.account.title")}>
          <Q q={t("sections.account.q1.q")}>
            <p>{t("sections.account.q1.a")}</p>
          </Q>
          <Q q={t("sections.account.q2.q")}>
            <p>{t("sections.account.q2.a")}</p>
          </Q>
          <Q q={t("sections.account.q3.q")}>
            <p>
              {t.rich("sections.account.q3.a", {
                a: (chunks) => (
                  <a
                    href="/data-deletion"
                    className="text-wine-accent underline"
                  >
                    {chunks}
                  </a>
                ),
              })}
            </p>
          </Q>
        </Section>

        {/* ── Glossário ── */}

        <Section id="glossario" title={t("sections.glossary.title")}>
          <dl>
            {GLOSSARY_KEYS.map((k) => (
              <Term key={k} term={t(`sections.glossary.terms.${k}.term`)}>
                {t(`sections.glossary.terms.${k}.def`)}
              </Term>
            ))}
          </dl>
        </Section>

        {/* ── Contato ── */}

        <Section id="contato" title={t("sections.contact.title")}>
          <p className="text-wine-muted text-sm mb-3">
            {t.rich("sections.contact.intro", {
              a: (chunks) => (
                <a
                  href="mailto:privacy@winegod.ai"
                  className="text-wine-accent underline"
                >
                  {chunks}
                </a>
              ),
            })}
          </p>
        </Section>

        {/* ── Versão ── */}

        <div className="mt-12 pt-6 border-t border-wine-border text-wine-muted text-xs">
          {t("footer.version")}
        </div>
      </div>
    </AppShell>
  );
}
