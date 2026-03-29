# CHAT J — WineCard + QuickButtons (Componentes Visuais do Chat)

## CONTEXTO
WineGod.ai e um chat com Baco (IA sommelier). O frontend Next.js ja existe em `C:\winegod-app\frontend\`. Atualmente as respostas aparecem so como texto. Voce vai criar componentes visuais pra exibir vinhos como CARDS bonitos dentro do chat.

## SUA TAREFA
1. Criar componente WineCard (card visual com dados do vinho)
2. Criar componente QuickButtons (botoes rapidos de acao)
3. Criar componente WineComparison (comparacao lado a lado)
4. Modificar MessageBubble pra renderizar cards quando a resposta contem dados de vinhos
5. Definir formato JSON que o backend envia quando tem vinhos pra exibir

## ONDE TRABALHAR
`C:\winegod-app\frontend\`

NAO toque no backend. NAO toque em outras pastas.

## ESTRUTURA A CRIAR

```
C:\winegod-app\frontend\components\
  wine/
    WineCard.tsx          <- Card individual de vinho
    WineComparison.tsx    <- Comparacao lado a lado (2-5 vinhos)
    QuickButtons.tsx      <- Botoes rapidos pos-resposta
    ScoreBadge.tsx        <- Badge visual da nota (estrela + numero)
    TermBadges.tsx        <- Badges dos termos (Paridade, Legado, etc.)
    PriceTag.tsx          <- Tag de preco com moeda
```

## FORMATO DE DADOS

O backend vai enviar respostas com este formato (dentro do texto ou como JSON separado):

```json
{
  "type": "wine_card",
  "wine": {
    "id": 12345,
    "nome": "Catena Zapata Malbec 2020",
    "produtor": "Bodega Catena Zapata",
    "safra": "2020",
    "tipo": "Tinto",
    "pais": "Argentina",
    "regiao": "Mendoza",
    "uvas": ["Malbec"],
    "nota": 4.18,
    "nota_tipo": "verified",
    "score": 4.52,
    "termos": ["Paridade", "Legado"],
    "preco_min": 25.00,
    "preco_max": 45.00,
    "moeda": "USD",
    "imagem_url": null,
    "total_fontes": 8
  }
}
```

Para comparacoes:
```json
{
  "type": "wine_comparison",
  "wines": [/* array de wine objects */]
}
```

## ESPECIFICACOES VISUAIS

### WineCard
```
┌─────────────────────────────────┐
│ [Imagem]  CATENA ZAPATA        │
│           MALBEC 2020          │
│           Bodega Catena Zapata │
│           Mendoza, Argentina   │
│                                │
│  4.18 ★  Paridade · Legado    │
│                                │
│  $25 - $45  ·  8 lojas        │
│                                │
│  [Onde comprar]  [Similares]   │
└─────────────────────────────────┘
```

Cores (seguir tema existente):
- Card background: #1A1A2E (mesmo das bolhas do Baco)
- Borda: #2A2A4E
- Nota verificada: cor branca normal
- Nota estimada: prefixo "~", cor levemente opaca
- Estrela: #FFD700 (dourado)
- Termos: badges pequenos com fundo #2A2A4E e texto #C0C0C0
- Preco: destaque #8B1A4A (vinho)
- Botoes: outline com cor accent #8B1A4A

Se nao tem imagem (imagem_url null): mostrar placeholder com icone de taca de vinho

### ScoreBadge
- Nota verificada: "4.18 ★"
- Nota estimada: "~3.85 ★" (com til, cor mais suave)
- Tamanho: destaque, maior que o resto do texto

### TermBadges
- Badges inline: "Paridade" "Legado" "Capilaridade" "Avaliacoes"
- Estilo: pills pequenos, fundo sutil, sem borda pesada
- Se nao tem termos: nao mostrar nada (sem "nenhum termo")

### PriceTag
- Mostrar faixa: "$25 - $45"
- Se so tem um preco: "$25"
- Se nao tem preco: "Preco indisponivel"
- Moeda formatada corretamente (USD, EUR, BRL, etc.)

### QuickButtons
Aparecem DEPOIS da resposta do Baco. Sao atalhos pra proximas acoes:
- [Comparar com outro] → envia "Compara esse com..."
- [Ver similares] → envia "Me mostra vinhos similares"
- [Mais barato] → envia "Tem algo mais barato na mesma qualidade?"
- [Onde comprar] → envia "Onde compro esse vinho?"

Estilo: botoes horizontais, scroll horizontal se nao caber, fundo transparente, borda #8B1A4A

### WineComparison
Lado a lado (desktop) ou empilhado (mobile). 2-5 vinhos.
Destacar em verde sutil o "melhor custo-beneficio" (maior score).

## PARSING DA RESPOSTA

O backend pode enviar dados de vinho de duas formas:

1. **JSON embutido no texto** (entre tags especiais):
```
Texto do Baco aqui...
<wine-card>{"type":"wine_card","wine":{...}}</wine-card>
Mais texto...
```

2. **Metadata separada** (no response JSON):
```json
{
  "response": "Texto do Baco...",
  "wines": [{"type": "wine_card", "wine": {...}}],
  "quick_buttons": ["Comparar", "Similares", "Mais barato"]
}
```

Implementar suporte pra AMBAS as formas. O MessageBubble deve:
1. Parsear o texto procurando `<wine-card>...</wine-card>`
2. Renderizar texto normal como markdown
3. Substituir tags wine-card pelo componente WineCard
4. Mostrar QuickButtons no final se houver

## RESPONSIVIDADE

- **Mobile** (< 640px): cards ocupam 100% da largura, comparacao empilhada
- **Desktop** (> 640px): cards max-width 400px, comparacao lado a lado

## O QUE NAO FAZER
- NAO alterar o backend
- NAO alterar globals.css (adicionar estilos via Tailwind classes)
- NAO instalar bibliotecas novas de UI (Tailwind puro)
- NAO criar paginas novas
- NAO fazer git commit/push
- NAO usar emojis no codigo

## COMO TESTAR

Adicionar dados mock temporarios no page.tsx pra testar os componentes:

```typescript
// Mock de wine card pra teste visual
const mockWineResponse = `Esse e um achado magnifico!
<wine-card>{"type":"wine_card","wine":{"id":1,"nome":"Catena Zapata Malbec 2020","produtor":"Bodega Catena Zapata","safra":"2020","tipo":"Tinto","pais":"Argentina","regiao":"Mendoza","uvas":["Malbec"],"nota":4.18,"nota_tipo":"verified","score":4.52,"termos":["Paridade","Legado"],"preco_min":25,"preco_max":45,"moeda":"USD","imagem_url":null,"total_fontes":8}}</wine-card>
Quer que eu compare com outro Malbec?`;
```

```bash
cd C:\winegod-app\frontend
npm run dev
```

Abrir http://localhost:3000, verificar:
1. Card aparece bonito dentro da bolha
2. Nota com estrela dourada
3. Badges de termos aparecem
4. Preco formatado
5. Botoes quickbuttons clicaveis
6. Funciona no celular (redimensionar browser)
7. Comparacao lado a lado funciona

## ENTREGAVEL
1. 6 componentes em `frontend/components/wine/`
2. MessageBubble atualizado pra parsear wine-cards
3. QuickButtons funcionando (enviam mensagem ao clicar)
4. Responsivo (mobile + desktop)
5. Mock de teste pra validacao visual
