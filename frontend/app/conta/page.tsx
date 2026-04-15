import type { Metadata } from "next";
import { ContaContent } from "./ContaContent";

export const metadata: Metadata = {
  title: "Minha Conta — winegod.ai",
  description: "Perfil, provider e configurações da sua conta no winegod.ai.",
};

export default function ContaPage() {
  return <ContaContent />;
}
