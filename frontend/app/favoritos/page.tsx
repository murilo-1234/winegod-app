import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { FavoritosContent } from "./FavoritosContent";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("favorites.meta");
  return {
    title: t("title"),
    description: t("description"),
  };
}

export default function FavoritosPage() {
  return <FavoritosContent />;
}
