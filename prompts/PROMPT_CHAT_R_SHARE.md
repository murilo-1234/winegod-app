# CHAT R — Compartilhamento (winegod.ai/c/xxx)

## CONTEXTO

WineGod.ai e uma IA sommelier global. Um chat web onde o personagem "Baco" responde sobre vinhos. O backend e Flask + Claude API, o frontend e Next.js.

Agora precisamos que o usuario possa **compartilhar resultados** em links como `chat.winegod.ai/c/abc123`. Quando alguem abrir esse link, ve um card bonito com os vinhos recomendados + og:image para preview no WhatsApp/Twitter/etc.

## SUA TAREFA

Implementar:
1. **Backend**: endpoint para salvar e recuperar compartilhamentos
2. **Frontend**: pagina /c/[id] que mostra os vinhos compartilhados
3. **Open Graph**: meta tags para preview bonito em redes sociais
4. **Botao "Compartilhar"**: no chat, apos recomendacoes do Baco

## CREDENCIAIS

```
# Banco WineGod no Render
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod
```

## ARQUIVOS A CRIAR

### 1. backend/routes/sharing.py (NOVO)

Blueprint Flask:
```python
sharing_bp = Blueprint('sharing', __name__)
```

Endpoints:

**POST /api/share** — Criar compartilhamento
```json
// Request
{
    "wine_ids": [123, 456, 789],
    "title": "Tintos argentinos ate R$100",
    "context": "Baco recomendou estes 3 vinhos para churrasco"
}

// Response
{
    "share_id": "abc123",
    "url": "https://chat.winegod.ai/c/abc123"
}
```

- Gerar ID curto (6-8 chars, base62: a-z A-Z 0-9)
- Salvar no banco
- Retornar URL

**GET /api/share/:id** — Recuperar compartilhamento
```json
// Response
{
    "share_id": "abc123",
    "title": "Tintos argentinos ate R$100",
    "context": "Baco recomendou estes 3 vinhos para churrasco",
    "wines": [
        {
            "id": 123,
            "nome": "Catena Malbec 2020",
            "produtor": "Bodega Catena Zapata",
            "pais_nome": "Argentina",
            "regiao": "Mendoza",
            "vivino_rating": 4.2,
            "nota_wcf": 4.35,
            "winegod_score": 3.87,
            "preco_min": 45.90,
            "preco_max": 89.00,
            "moeda": "BRL"
        }
    ],
    "created_at": "2026-03-27T18:30:00Z"
}
```

- Buscar compartilhamento + dados dos vinhos com JOIN
- Retornar 404 se nao existir

### 2. backend/db/models_share.py (NOVO)

Tabela e funcoes:

```sql
CREATE TABLE IF NOT EXISTS shares (
    id VARCHAR(8) PRIMARY KEY,
    title VARCHAR(255),
    context TEXT,
    wine_ids INTEGER[] NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    view_count INTEGER DEFAULT 0
);

CREATE INDEX idx_shares_created ON shares (created_at DESC);
```

Funcoes:
- `create_tables_share()` — cria tabela
- `create_share(title, context, wine_ids)` — gera ID curto, insere, retorna ID
- `get_share(share_id)` — busca compartilhamento + dados dos vinhos
- `increment_views(share_id)` — incrementa view_count

Usar `get_connection()` e `release_connection()` de `db.connection`:
```python
from db.connection import get_connection, release_connection
```

Gerador de ID curto:
```python
import secrets
import string

def generate_share_id():
    alphabet = string.ascii_letters + string.digits  # a-zA-Z0-9
    return ''.join(secrets.choice(alphabet) for _ in range(7))
```

### 3. frontend/app/c/[id]/page.tsx (NOVO)

Pagina Next.js server-side rendered para o link compartilhado.

**Layout:**
- Header: logo winegod.ai + botao "Abrir no Chat"
- Titulo do compartilhamento (ex: "Tintos argentinos ate R$100")
- Contexto/descricao (ex: "Baco recomendou estes 3 vinhos para churrasco")
- Lista de WineCards (reusar componente existente de `frontend/components/wine/WineCard.tsx`)
- Footer: "Descubra mais vinhos em chat.winegod.ai"

**Estilo:**
- Dark theme igual ao chat (bg #0D0D1A, card #1A1A2E)
- Responsivo (mobile first)
- Bonito o suficiente para ser compartilhado

**Dados:**
- Usar `generateMetadata()` do Next.js para meta tags dinamicas
- Fetch dados do backend: `GET /api/share/:id`
- Se nao existir: mostrar pagina 404 "Compartilhamento nao encontrado"

### 4. frontend/app/c/[id]/opengraph-image.tsx (NOVO — OPCIONAL)

Se possivel, usar Next.js OG image generation (`next/og` ImageResponse) para gerar og:image dinamica:
- Fundo escuro (#0D0D1A)
- Logo winegod.ai no topo
- Titulo do compartilhamento
- Lista de 1-3 nomes de vinhos com notas
- Texto: "Recomendado por Baco, o sommelier IA"
- Tamanho: 1200x630

Se `next/og` der muito trabalho, usar meta tags estaticas com uma imagem padrao.

### 5. frontend/app/c/[id]/layout.tsx (NOVO)

Layout com metadata dinamica:
```typescript
export async function generateMetadata({ params }) {
    // Fetch share data
    // Return: title, description, openGraph (title, description, images, url)
}
```

### 6. frontend/components/ShareButton.tsx (NOVO)

Componente botao "Compartilhar" para usar no chat:
- Icone de compartilhamento (link/share)
- Ao clicar: chama POST /api/share com os wine_ids da mensagem
- Recebe URL → copia pro clipboard (navigator.clipboard.writeText)
- Mostra toast "Link copiado!"
- Props: `wine_ids: number[]`, `title?: string`, `context?: string`

**NAO integrar no MessageBubble** — deixar o componente pronto, o CTO integra depois.

## O QUE NAO FAZER

- **NAO modificar app.py** — o CTO registra blueprint depois
- **NAO modificar MessageBubble.tsx** — criar ShareButton isolado, CTO integra
- **NAO modificar nenhum componente wine/ existente** — reusar via import
- **NAO fazer git commit/push** — avisar quando terminar
- **NAO implementar autenticacao** — outro chat faz isso
- **NAO criar APIs de analytics** — so o view_count basico

## COMO TESTAR

1. Criar tabela:
```bash
cd backend
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod python -c "
from db.models_share import create_tables_share
create_tables_share()
print('Tabela shares criada')
"
```

2. Testar criar compartilhamento:
```bash
curl -X POST http://localhost:5000/api/share \
  -H "Content-Type: application/json" \
  -d '{"wine_ids": [1, 2, 3], "title": "Teste", "context": "Vinhos de teste"}'
```

3. Testar recuperar:
```bash
curl http://localhost:5000/api/share/ABC1234
```

4. Frontend compila:
```bash
cd frontend && npm run build
```

5. Testar pagina: abrir http://localhost:3000/c/ABC1234

## ENTREGAVEL

Quando terminar, deve existir:
- `backend/routes/sharing.py` — endpoints POST/GET share
- `backend/db/models_share.py` — tabela shares + funcoes
- `frontend/app/c/[id]/page.tsx` — pagina do compartilhamento
- `frontend/app/c/[id]/layout.tsx` — metadata OG dinamica
- `frontend/app/c/[id]/opengraph-image.tsx` — OG image (se viavel)
- `frontend/components/ShareButton.tsx` — botao compartilhar
- Documentacao de integracao (quais linhas adicionar em app.py, MessageBubble.tsx)

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificou nesta sessao. NUNCA incluir arquivos de outros chats. Fazer `git pull` antes de `git push` para nao conflitar com outros chats que rodam em paralelo.
