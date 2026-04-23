import { permanentRedirect } from "next/navigation";
import { getLocale } from "next-intl/server";
import { buildLegalPath } from "@/lib/legal-routing";

export default async function LegacyTermsPage() {
  permanentRedirect(buildLegalPath(await getLocale(), "terms"));
}
