import { permanentRedirect } from "next/navigation";
import { getLocale } from "next-intl/server";
import { buildLegalPath } from "@/lib/legal-routing";

// F7.5 - redirect permanente para rota canonica /legal/...
// O componente interativo DeleteAccountSection e renderizado pela rota
// canonica /legal/[country]/[lang]/data-deletion via placeholder no
// markdown. Aqui apenas redirecionamos.
export default async function LegacyDataDeletionPage() {
  permanentRedirect(buildLegalPath(await getLocale(), "data-deletion"));
}
