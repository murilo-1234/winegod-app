import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = {
  title: "Política de Privacidade — winegod.ai",
  description:
    "Como o winegod.ai coleta, usa e protege seus dados pessoais.",
};

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Política de Privacidade"
      description="Como o winegod.ai coleta, usa e protege seus dados."
      lastUpdated="13 de abril de 2026"
    >
      <h2>1. Quem somos</h2>
      <p>
        O <strong>winegod.ai</strong> é um serviço de inteligência artificial
        focado em vinhos, acessível em{" "}
        <a href="https://chat.winegod.ai">chat.winegod.ai</a>. Este documento
        descreve como tratamos os dados de quem usa o produto.
      </p>

      <h2>2. Dados que coletamos</h2>

      <h3>2.1 Dados de conta (login via OAuth)</h3>
      <p>
        Quando você faz login com Google, Facebook, Apple ou Microsoft,
        recebemos do provedor escolhido: nome, e-mail e foto de perfil. Não
        temos acesso à sua senha.
      </p>

      <h3>2.2 Dados de uso</h3>
      <ul>
        <li>Mensagens enviadas ao chat (texto, fotos, vídeos e PDFs)</li>
        <li>Registro de créditos consumidos (quantidade, tipo e data)</li>
        <li>Identificador de sessão e endereço IP</li>
      </ul>

      <h3>2.3 Armazenamento local</h3>
      <p>
        Usamos <strong>localStorage</strong> e <strong>sessionStorage</strong>{" "}
        no seu navegador para manter a sessão ativa e exibir o histórico de
        mensagens da sessão atual. Esses dados ficam apenas no seu dispositivo.
      </p>

      <h2>3. Como usamos seus dados</h2>
      <ul>
        <li>Fornecer respostas personalizadas sobre vinhos</li>
        <li>Controlar créditos de uso (limite diário)</li>
        <li>Melhorar a qualidade do serviço</li>
      </ul>
      <p>
        <strong>Não vendemos seus dados pessoais.</strong>
      </p>

      <h2>4. Serviços de terceiros</h2>
      <p>Para funcionar, o winegod.ai utiliza serviços externos:</p>
      <ul>
        <li>
          <strong>Anthropic (Claude)</strong> — processamento de linguagem
          natural para o chat
        </li>
        <li>
          <strong>Google (Gemini)</strong> — leitura visual de fotos e PDFs
          (OCR)
        </li>
        <li>
          <strong>Google, Facebook, Apple, Microsoft</strong> — autenticação via
          OAuth
        </li>
        <li>
          <strong>Render</strong> — hospedagem do backend e banco de dados
        </li>
        <li>
          <strong>Vercel</strong> — hospedagem do frontend
        </li>
      </ul>
      <p>
        Cada serviço possui sua própria política de privacidade. As mensagens
        enviadas ao chat são processadas pela Anthropic e, no caso de fotos e
        PDFs, também pelo Google Gemini.
      </p>

      <h2>5. Retenção de dados</h2>
      <p>
        Seus dados de conta permanecem enquanto sua conta existir. Os registros
        de uso (créditos consumidos) são mantidos para controle interno. Você
        pode solicitar a exclusão dos seus dados conforme descrito na página{" "}
        <a href="/data-deletion">Exclusão de dados</a>.
      </p>

      <h2>6. Seus direitos</h2>
      <p>Você pode:</p>
      <ul>
        <li>Solicitar acesso aos seus dados pessoais</li>
        <li>Solicitar correção de dados incorretos</li>
        <li>Solicitar exclusão da sua conta e dados associados</li>
      </ul>
      <p>
        Para exercer esses direitos, entre em contato pelo e-mail{" "}
        <a href="mailto:privacy@winegod.ai">privacy@winegod.ai</a>.
      </p>

      <h2>7. Alterações</h2>
      <p>
        Esta política pode ser atualizada. A data no topo da página indica a
        última alteração. O uso continuado do serviço após alterações constitui
        aceitação.
      </p>
    </LegalPage>
  );
}
