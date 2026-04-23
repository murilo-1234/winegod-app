import { permanentRedirect } from "next/navigation";
import { cookies, headers } from "next/headers";

// F7.5 - redirect permanente para rota canonica /legal/...
// O componente interativo DeleteAccountSection e renderizado pela rota
// canonica /legal/[country]/[lang]/data-deletion via placeholder no
// markdown. Aqui apenas redirecionamos.
async function resolveLegacyLocale(): Promise<string | undefined> {
  const headerStore = await headers();
  const headerLocale =
    headerStore.get("X-NEXT-INTL-LOCALE") ??
    headerStore.get("x-next-intl-locale");
  if (headerLocale) return headerLocale;
  const cookieStore = await cookies();
  return cookieStore.get("wg_locale_choice")?.value;
}

export default async function LegacyDataDeletionPage() {
  const locale = await resolveLegacyLocale();
  if (locale === "pt-BR") {
    permanentRedirect("/legal/BR/pt-BR/data-deletion");
  }
  permanentRedirect("/legal/DEFAULT/en-US/data-deletion");
}
