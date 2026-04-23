import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { ContaContent } from "./ContaContent";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("account.meta");
  return {
    title: t("title"),
    description: t("description"),
  };
}

export default function ContaPage() {
  return <ContaContent />;
}
