import type { Metadata } from "next";
import { Inter, Playfair_Display } from "next/font/google";
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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body className={`${inter.className} ${playfair.variable}`}>{children}</body>
    </html>
  );
}
