import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Ajuda — winegod.ai",
  description: "Perguntas frequentes, glossário e contato do winegod.ai.",
};

/* ── Subcomponentes locais ── */

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <h2 className="font-display text-lg font-bold text-wine-text mt-10 mb-4">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Q({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <h3 className="font-semibold text-wine-text text-sm mb-1">{q}</h3>
      <div className="text-wine-muted text-sm leading-relaxed">{children}</div>
    </div>
  );
}

function Term({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <dt className="font-semibold text-wine-text text-sm">{term}</dt>
      <dd className="text-wine-muted text-sm leading-relaxed ml-0">
        {children}
      </dd>
    </div>
  );
}

/* ── Página ── */

export default function AjudaPage() {
  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-4 py-8 overflow-y-auto h-full">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-1">
          Ajuda
        </h1>
        <p className="text-wine-muted text-sm mb-6">
          Tudo que você precisa saber para usar o winegod.ai.
        </p>

        {/* ── Índice rápido ── */}
        <nav className="mb-8 text-sm flex flex-wrap gap-x-4 gap-y-1">
          {[
            ["#chat", "Chat"],
            ["#fotos", "Fotos e PDF"],
            ["#notas", "Notas e score"],
            ["#creditos", "Créditos"],
            ["#compartilhar", "Compartilhar"],
            ["#conta", "Conta"],
            ["#glossario", "Glossário"],
            ["#contato", "Contato"],
          ].map(([href, label]) => (
            <a
              key={href}
              href={href}
              className="text-wine-accent hover:underline"
            >
              {label}
            </a>
          ))}
        </nav>

        {/* ── FAQ ── */}

        <Section id="chat" title="Como usar o chat">
          <Q q="O que é o winegod.ai?">
            <p>
              É um assistente de inteligência artificial especializado em
              vinhos. Você conversa com o Baco — o deus do vinho — e ele
              responde sobre rótulos, recomendações, comparações e muito mais.
            </p>
          </Q>
          <Q q="Que tipo de pergunta posso fazer?">
            <p>Qualquer coisa sobre vinho. Alguns exemplos:</p>
            <ul className="list-disc pl-5 mt-1 space-y-0.5">
              <li>Me recomenda um tinto até R$ 80</li>
              <li>O que combina com risoto de cogumelos?</li>
              <li>Compara Malbec argentino e Carménère chileno</li>
              <li>Esse rótulo é bom? (com foto)</li>
            </ul>
          </Q>
          <Q q="Em que idioma posso conversar?">
            <p>
              O Baco responde no idioma em que você escrever. Português, inglês,
              espanhol, francês e outros.
            </p>
          </Q>
        </Section>

        <Section id="fotos" title="Fotos, OCR e PDF">
          <Q q="Posso enviar foto de um rótulo?">
            <p>
              Sim. Tire uma foto do rótulo e envie pelo chat. O Baco lê a
              imagem, identifica o vinho e busca informações na base de dados.
            </p>
          </Q>
          <Q q="E foto de prateleira ou cardápio?">
            <p>
              Também funciona. O sistema identifica os vinhos visíveis na
              imagem. Funciona melhor com fotos nítidas e bem iluminadas.
            </p>
          </Q>
          <Q q="Posso enviar PDF de carta de vinhos?">
            <p>
              Sim. O Baco extrai os vinhos listados no PDF, busca cada um na
              base e responde com o que encontrar. PDFs muito longos podem ser
              processados parcialmente.
            </p>
          </Q>
          <Q q="Quantas fotos posso enviar de uma vez?">
            <p>Até 5 imagens por mensagem.</p>
          </Q>
        </Section>

        <Section id="notas" title="Notas e score">
          <Q q="O que é a nota do vinho?">
            <p>
              É uma avaliação de qualidade numa escala de 0 a 5. Pode ser
              baseada em dados públicos de avaliações reais ou estimada pelo
              sistema quando há poucos dados disponíveis.
            </p>
          </Q>
          <Q q="O que é o WineGod Score?">
            <p>
              É um índice de custo-benefício próprio do winegod.ai. Leva em
              conta a nota de qualidade, o preço e micro-ajustes. Quanto maior,
              melhor o custo-benefício.
            </p>
          </Q>
          <Q q="Quando o Baco diz que 'não tem nota', o que significa?">
            <p>
              Significa que o vinho existe na base mas não tem avaliações
              suficientes para gerar uma nota confiável. O Baco não inventa
              nota — se não tem, ele diz.
            </p>
          </Q>
        </Section>

        <Section id="creditos" title="Créditos">
          <Q q="Quantas mensagens posso enviar?">
            <p>
              Visitantes (sem login) têm <strong>5 mensagens por sessão</strong>
              . Usuários logados têm <strong>15 mensagens por dia</strong>,
              renovadas à meia-noite UTC.
            </p>
          </Q>
          <Q q="Fotos e PDFs custam mais?">
            <p>
              Uma foto avulsa custa 1 crédito. Enviar de 2 a 5 fotos de uma
              vez, um vídeo ou um PDF custa 3 créditos.
            </p>
          </Q>
          <Q q="Como ganho mais créditos?">
            <p>
              Faça login com Google, Facebook, Apple ou Microsoft. Você passa de
              5 para 15 mensagens por dia, renovadas automaticamente.
            </p>
          </Q>
        </Section>

        <Section id="compartilhar" title="Compartilhamento">
          <Q q="Posso compartilhar uma seleção de vinhos?">
            <p>
              Sim. Quando o Baco lista vinhos, aparece um botão de compartilhar.
              Ele gera um link público com a seleção, que qualquer pessoa pode
              abrir sem login.
            </p>
          </Q>
        </Section>

        <Section id="conta" title="Conta e login">
          <Q q="Preciso criar conta?">
            <p>
              Não. Você pode usar o chat como visitante. Mas o login dá mais
              créditos e, no futuro, acesso a recursos adicionais.
            </p>
          </Q>
          <Q q="Com quais provedores posso entrar?">
            <p>Google, Facebook, Apple e Microsoft.</p>
          </Q>
          <Q q="Como excluo minha conta?">
            <p>
              Se você estiver logado, pode excluir sua conta diretamente na
              página{" "}
              <a href="/data-deletion" className="text-wine-accent underline">
                Exclusão de dados
              </a>
              . Se preferir, também há fallback por e-mail.
            </p>
          </Q>
        </Section>

        {/* ── Glossário ── */}

        <Section id="glossario" title="Glossário">
          <dl>
            <Term term="Baco">
              O personagem do winegod.ai — deus do vinho na mitologia. É quem
              responde suas perguntas.
            </Term>
            <Term term="Rótulo (label)">
              A etiqueta colada na garrafa. Contém nome do vinho, produtor,
              safra, região e teor alcoólico.
            </Term>
            <Term term="Safra (vintage)">
              O ano em que as uvas foram colhidas. Nem todo vinho tem safra
              (vinhos non-vintage são misturas de anos).
            </Term>
            <Term term="Terroir">
              Conjunto de clima, solo e práticas locais que dão caráter único a
              um vinho de determinada região.
            </Term>
            <Term term="Tanino">
              Substância presente na casca, sementes e engaços da uva. Dá
              sensação de secura e estrutura ao vinho tinto.
            </Term>
            <Term term="Corpo">
              Sensação de peso do vinho na boca. Pode ser leve, médio ou
              encorpado.
            </Term>
            <Term term="Acidez">
              Frescor do vinho. Vinhos com boa acidez parecem vivos e
              equilibrados.
            </Term>
            <Term term="Seco / doce">
              Seco = sem açúcar residual perceptível. Doce = com dulçor
              evidente. Existem níveis intermediários (meio-seco, suave).
            </Term>
            <Term term="Blend">
              Vinho feito com mais de uma variedade de uva. Ex: Cabernet
              Sauvignon + Merlot.
            </Term>
            <Term term="Varietal">
              Vinho feito predominantemente com uma única uva. Ex: 100% Malbec.
            </Term>
            <Term term="Decantação">
              Transferir o vinho da garrafa para um decanter para aerar e
              separar sedimentos.
            </Term>
            <Term term="OCR">
              Reconhecimento óptico de caracteres. Tecnologia usada pelo
              winegod.ai para ler textos em fotos e PDFs.
            </Term>
            <Term term="WineGod Score">
              Índice de custo-benefício do winegod.ai. Combina qualidade e preço
              numa escala de 0 a 5.
            </Term>
            <Term term="Nota WCF">
              Nota de qualidade pura usada internamente. Base para o cálculo do
              WineGod Score.
            </Term>
            <Term term="Crédito">
              Unidade de uso do chat. Cada mensagem consome 1 ou mais créditos
              dependendo do tipo de mídia enviada.
            </Term>
            <Term term="Produtor">
              Vinícola ou empresa que elabora o vinho. Ex: Catena Zapata, Penfolds.
            </Term>
          </dl>
        </Section>

        {/* ── Contato ── */}

        <Section id="contato" title="Contato">
          <p className="text-wine-muted text-sm mb-3">
            Para dúvidas, sugestões ou problemas, escreva para{" "}
            <a
              href="mailto:privacy@winegod.ai"
              className="text-wine-accent underline"
            >
              privacy@winegod.ai
            </a>
            .
          </p>
        </Section>

        {/* ── Versão ── */}

        <div className="mt-12 pt-6 border-t border-wine-border text-wine-muted text-xs">
          winegod.ai · v0.1.0 beta · Abril 2026
        </div>
      </div>
    </AppShell>
  );
}
