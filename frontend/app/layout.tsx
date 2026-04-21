import type { Metadata } from "next";
import { Inter, Playfair_Display } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });
const playfair = Playfair_Display({
  subsets: ["latin"],
  weight: ["700", "900"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "winegod.ai — Wine Intelligence, Powered by Gods",
  description: "Your personal wine god. Find the best wines for your budget. Photo, voice, or text — just ask.",
  icons: { icon: "/favicon.ico" },
  openGraph: {
    title: "winegod.ai — Wine Intelligence, Powered by Gods",
    description: "Your personal wine god. Find the best wines for your budget. Photo, voice, or text — just ask.",
    type: "website",
    url: "https://chat.winegod.ai",
    siteName: "winegod.ai",
  },
  twitter: {
    card: "summary_large_image",
    title: "winegod.ai — Wine Intelligence, Powered by Gods",
    description: "Your personal wine god. Find the best wines for your budget. Photo, voice, or text — just ask.",
  },
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // F2.3b: locale e messages vem do request config (frontend/i18n/request.ts).
  // F2.4 substituira o stub por resolucao real (cookie wg_locale_choice,
  // header geo, fallback chain). Nesta fase, garante que useTranslations()
  // funciona em todas as rotas sem prefixo (/, /chat/[id], /conta, etc.).
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale}>
      <body className={`${inter.className} ${playfair.variable}`}>
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
