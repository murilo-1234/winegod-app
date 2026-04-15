import type { Metadata } from "next";
import { FavoritosContent } from "./FavoritosContent";

export const metadata: Metadata = {
  title: "Conversas salvas — winegod.ai",
  description: "Suas conversas salvas no winegod.ai.",
};

export default function FavoritosPage() {
  return <FavoritosContent />;
}
