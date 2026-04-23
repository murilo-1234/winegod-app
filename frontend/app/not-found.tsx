import Link from "next/link";
import { getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations("notFound");
  return (
    <div className="flex flex-col items-center justify-center h-dvh bg-wine-bg px-4 text-center">
      <img src="/logo.png" alt="winegod.ai" className="h-16 w-auto mb-6" />
      <h1 className="font-display text-3xl font-bold text-wine-text mb-2">
        {t("title")}
      </h1>
      <p className="text-wine-muted text-sm mb-8 max-w-md">
        {t("description")}
      </p>
      <Link
        href="/"
        className="px-5 py-2.5 bg-wine-accent text-white rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
      >
        {t("cta")}
      </Link>
    </div>
  );
}
