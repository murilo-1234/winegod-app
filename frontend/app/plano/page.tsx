import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { PlanoContent } from "./PlanoContent";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("plan.meta");
  return {
    title: t("title"),
    description: t("description"),
  };
}

export default function PlanoPage() {
  return <PlanoContent />;
}
