import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = {
  title: "Termos de Uso — winegod.ai",
  description: "Termos e condições de uso do winegod.ai.",
};

export default function TermsPage() {
  return (
    <LegalPage
      title="Termos de Uso"
      description="Condições para utilização do winegod.ai."
      lastUpdated="13 de abril de 2026"
    >
      <h2>1. Aceitação</h2>
      <p>
        Ao usar o <strong>winegod.ai</strong> (acessível em{" "}
        <a href="https://chat.winegod.ai">chat.winegod.ai</a>), você concorda
        com estes termos. Se não concordar, não utilize o serviço.
      </p>

      <h2>2. O que é o serviço</h2>
      <p>
        O winegod.ai é um assistente de inteligência artificial especializado em
        vinhos. Ele responde perguntas, analisa fotos de rótulos e cardápios, e
        oferece recomendações com base em uma base de dados de vinhos.
      </p>

      <h2>3. Natureza das respostas</h2>
      <p>
        As respostas do winegod.ai são <strong>informativas</strong> e geradas
        por inteligência artificial. Elas não constituem consultoria
        profissional, médica ou financeira. Notas, scores e recomendações são
        baseados em dados disponíveis e podem conter imprecisões.
      </p>
      <p>
        <strong>
          Use as informações como referência, não como verdade absoluta.
        </strong>
      </p>

      <h2>4. Conta e acesso</h2>
      <ul>
        <li>
          O acesso como visitante (guest) é limitado a um número reduzido de
          mensagens por sessão.
        </li>
        <li>
          O login via Google, Facebook, Apple ou Microsoft concede créditos
          adicionais, renovados diariamente.
        </li>
        <li>
          Você é responsável pela segurança da sua conta no provedor OAuth
          utilizado.
        </li>
      </ul>

      <h2>5. Uso aceitável</h2>
      <p>Ao usar o winegod.ai, você concorda em:</p>
      <ul>
        <li>Não utilizar o serviço para fins ilegais</li>
        <li>Não tentar explorar, sobrecarregar ou interferir no serviço</li>
        <li>Não enviar conteúdo ofensivo, ilegal ou que viole direitos de terceiros</li>
      </ul>

      <h2>6. Propriedade intelectual</h2>
      <p>
        O nome winegod.ai, o personagem Baco e a interface do produto são de
        titularidade dos seus criadores. Os dados de vinhos apresentados
        pertencem às suas respectivas fontes.
      </p>

      <h2>7. Limitação de responsabilidade</h2>
      <p>
        O serviço é fornecido <strong>como está</strong> (&quot;as is&quot;),
        sem garantias de disponibilidade contínua, precisão absoluta ou
        adequação a um fim específico. O winegod.ai não se responsabiliza por
        decisões de compra baseadas exclusivamente nas respostas do assistente.
      </p>

      <h2>8. Privacidade</h2>
      <p>
        O uso dos seus dados pessoais é regido pela nossa{" "}
        <a href="/privacy">Política de Privacidade</a>. Informações sobre
        exclusão de dados estão na página{" "}
        <a href="/data-deletion">Exclusão de dados</a>.
      </p>

      <h2>9. Alterações</h2>
      <p>
        Estes termos podem ser atualizados. A data no topo da página indica a
        última alteração. O uso continuado do serviço após alterações constitui
        aceitação.
      </p>
    </LegalPage>
  );
}
