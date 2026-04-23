import { permanentRedirect } from "next/navigation";
import { cookies, headers } from "next/headers";

// F7.5 - redirect permanente para rota canonica /legal/...
// Resolve o locale efetivo via:
//   1. header X-NEXT-INTL-LOCALE (setado pelo middleware quando a URL usa
//      prefixo /en, /es ou /fr antes do rewrite interno).
//   2. cookie wg_locale_choice (escolha manual persistente).
// Mapeia para a celula publicada: pt-BR -> BR/pt-BR; restante -> DEFAULT/en-US.
async function resolveLegacyLocale(): Promise<string | undefined> {
  const headerStore = await headers();
  const headerLocale =
    headerStore.get("X-NEXT-INTL-LOCALE") ??
    headerStore.get("x-next-intl-locale");
  if (headerLocale) return headerLocale;
  const cookieStore = await cookies();
  return cookieStore.get("wg_locale_choice")?.value;
}

export default async function LegacyPrivacyPage() {
  const locale = await resolveLegacyLocale();
  if (locale === "pt-BR") {
    permanentRedirect("/legal/BR/pt-BR/privacy");
  }
  permanentRedirect("/legal/DEFAULT/en-US/privacy");
}
