# Teste de Qualidade do Baco — Perguntas e Respostas

## Sua Tarefa

Voce vai testar o chatbot Baco (winegod.ai) fazendo perguntas reais e coletando as respostas. O resultado final sera um documento Markdown com todas as perguntas e respostas, pronto pra analise humana.

## Passo a Passo

### 1. Pedir o arquivo de perguntas

Pergunte ao usuario:
> "Qual o caminho do arquivo com as perguntas? (pode ser .txt ou .md, uma pergunta por linha)"

Espere o usuario responder com o caminho do arquivo. Leia o arquivo e extraia as perguntas. Aceite estes formatos:
- Uma pergunta por linha (texto puro)
- Linhas numeradas: `1. pergunta aqui` ou `1) pergunta aqui`
- Ignore linhas vazias, linhas que comecam com `#` (headers), e linhas que comecam com `>` (quotes)

Confirme com o usuario quantas perguntas foram encontradas antes de continuar:
> "Encontrei X perguntas. Vou enviar todas para o Baco em chat.winegod.ai. Isso pode levar alguns minutos. Confirma?"

### 2. Enviar as perguntas para a API

Use um script Python para enviar cada pergunta para a API do Baco e coletar as respostas.

**Endpoint:** `POST https://winegod-app.onrender.com/api/chat`

**Request:**
```json
{"message": "pergunta aqui", "session_id": "uuid-aleatorio"}
```

**Response:**
```json
{"response": "resposta do baco", "session_id": "...", "model": "..."}
```

**Regras de execucao:**
- Gerar um `session_id` (UUID) novo a cada 4 perguntas (o sistema tem limite de 5 mensagens por sessao guest)
- Esperar 2 segundos entre cada pergunta (rate limiting)
- Se receber status 429 (rate limited): esperar 5 segundos, gerar novo session_id, tentar de novo
- Se receber erro: anotar "ERRO" na resposta e continuar com a proxima
- Timeout de 120 segundos por pergunta
- Mostrar progresso no terminal: `[1/50] pergunta... OK` ou `ERRO`

**Script base para usar:**

```python
import requests
import uuid
import time
import sys

API_URL = "https://winegod-app.onrender.com/api/chat"

def ask_baco(question, session_id):
    try:
        resp = requests.post(
            API_URL,
            json={"message": question, "session_id": session_id},
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        if resp.status_code == 429:
            return {"error": "rate_limited", "status": 429}
        if resp.status_code != 200:
            return {"error": resp.text, "status": resp.status_code}
        return resp.json()
    except requests.exceptions.Timeout:
        return {"error": "timeout", "status": 0}
    except Exception as e:
        return {"error": str(e), "status": 0}

def run_test(perguntas, output_file):
    total = len(perguntas)
    results = []
    session_id = str(uuid.uuid4())
    session_count = 0
    errors = 0

    for i, pergunta in enumerate(perguntas, 1):
        if session_count >= 4:
            session_id = str(uuid.uuid4())
            session_count = 0

        print(f"[{i}/{total}] {pergunta[:60]}...", end=" ", flush=True)

        resp = ask_baco(pergunta, session_id)
        session_count += 1

        if resp.get("status") == 429:
            print("RATE LIMITED, retry...", end=" ", flush=True)
            time.sleep(5)
            session_id = str(uuid.uuid4())
            session_count = 0
            resp = ask_baco(pergunta, session_id)
            session_count += 1

        if "error" in resp:
            resposta = f"**ERRO:** {resp['error']}"
            modelo = "erro"
            errors += 1
            print("ERRO")
        else:
            resposta = resp.get("response", "(sem resposta)")
            modelo = resp.get("model", "?")
            print(f"OK ({modelo})")

        results.append({
            "num": i,
            "pergunta": pergunta,
            "resposta": resposta,
            "modelo": modelo,
        })

        time.sleep(2)

    # Gerar documento
    lines = []
    lines.append(f"# Teste Baco — {total} Perguntas com Respostas\n")
    lines.append(f"> Gerado automaticamente em {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> Total: {total} perguntas | Erros: {errors}\n")
    lines.append("---\n")

    for r in results:
        lines.append(f"### {r['num']}. {r['pergunta']}\n")
        lines.append(f"{r['resposta']}\n")
        lines.append(f"*Modelo: {r['modelo']}*\n")
        lines.append("---\n")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nPronto! {total} perguntas, {errors} erros.")
    print(f"Resultado: {output_file}")
    return errors
```

### 3. Gerar o documento final

O arquivo de saida deve ser salvo em `scripts/baco_test_results_YYYYMMDD_HHMM.md` (com data e hora atual).

Formato do documento:

```markdown
# Teste Baco — N Perguntas com Respostas

> Gerado automaticamente em YYYY-MM-DD HH:MM
> Total: N perguntas | Erros: X

---

### 1. texto da pergunta

texto completo da resposta do baco

*Modelo: claude-haiku-4-5-20251001*

---

### 2. texto da pergunta

texto completo da resposta do baco

*Modelo: claude-haiku-4-5-20251001*

---
```

### 4. Resumo final

Depois de gerar o documento, mostre ao usuario:
- Quantas perguntas foram enviadas
- Quantas tiveram resposta OK vs erro
- Caminho do arquivo gerado
- Pergunte se quer abrir ou revisar alguma resposta especifica
