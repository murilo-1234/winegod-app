import type { Metadata } from "next";
import { PlanoContent } from "./PlanoContent";

export const metadata: Metadata = {
  title: "Plano & Créditos — winegod.ai",
  description: "Veja seus créditos, uso diário e informações do plano no winegod.ai.",
};

export default function PlanoPage() {
  return <PlanoContent />;
}
