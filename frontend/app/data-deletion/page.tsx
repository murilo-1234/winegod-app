import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { DeleteAccountSection } from "./DeleteAccountSection";

export const metadata: Metadata = {
  title: "Exclusão de Dados — winegod.ai",
  description:
    "Como solicitar a exclusão dos seus dados pessoais no winegod.ai.",
};

export default function DataDeletionPage() {
  return (
    <LegalPage
      title="Exclusão de Dados"
      description="Como solicitar a remoção dos seus dados pessoais."
      lastUpdated="13 de abril de 2026"
    >
      <h2>Seus dados, sua escolha</h2>
      <p>
        Você tem o direito de solicitar a exclusão dos dados pessoais associados
        à sua conta no <strong>winegod.ai</strong>.
      </p>

      <h2>O que é excluído</h2>
      <p>Ao excluir sua conta, removemos permanentemente:</p>
      <ul>
        <li>Seus dados de perfil (nome, e-mail, foto de perfil)</li>
        <li>O vínculo com o provedor de login (Google, Facebook, Apple ou Microsoft)</li>
        <li>Todo o seu histórico de conversas com o Baco</li>
        <li>Todas as suas conversas salvas (favoritos)</li>
      </ul>

      <h2>O que não é excluído</h2>
      <ul>
        <li>
          Registros de uso anonimizados (sem vínculo com sua conta) que
          mantemos para análise agregada do produto
        </li>
        <li>
          Dados armazenados localmente no seu navegador — esses são limpos
          automaticamente ao excluir a conta, mas você também pode limpar
          manualmente nas configurações do navegador
        </li>
      </ul>

      <h2>Excluir sua conta</h2>
      <DeleteAccountSection />

      <h2>Dados em serviços de terceiros</h2>
      <p>
        Ao excluir sua conta no winegod.ai, removemos seus dados dos nossos
        sistemas. Para revogar o acesso do winegod.ai à sua conta no provedor de
        login, acesse as configurações de segurança do próprio provedor:
      </p>
      <ul>
        <li>
          <strong>Google:</strong> Configurações da conta &gt; Segurança &gt;
          Apps de terceiros
        </li>
        <li>
          <strong>Facebook:</strong> Configurações &gt; Apps e sites
        </li>
        <li>
          <strong>Apple:</strong> Ajustes &gt; ID Apple &gt; Apps que usam o
          ID Apple
        </li>
        <li>
          <strong>Microsoft:</strong> Conta &gt; Privacidade &gt; Apps e
          serviços
        </li>
      </ul>

      <h2>Dúvidas</h2>
      <p>
        Para qualquer dúvida sobre exclusão de dados ou privacidade, entre em
        contato pelo e-mail{" "}
        <a href="mailto:privacy@winegod.ai">privacy@winegod.ai</a>.
      </p>
    </LegalPage>
  );
}
