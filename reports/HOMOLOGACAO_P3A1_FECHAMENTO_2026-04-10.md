# Fechamento P3A.1 — Re-homologacao Posada + Cambio

Data: 2026-04-10 19:18

---

## Evidencia

### Regressao (criterio de pronto)
- `python C:\winegod-app\backend\tests\test_pdf_pipeline.py` → **19/19 PASS** (9 antigos + 10 P3A.1)
- `python C:\winegod-app\backend\tests\test_item_status.py` → **17/17 PASS**
- `python C:\winegod-app\backend\tests\test_resolver_line_matching.py` → **88/88 PASS**

### Mudanca em chat.py
Mapeamento explicito de `extraction_method="native_text_chunked"`:
```
"Texto extraido do PDF em partes apos falha do parse inicial
 (confianca moderada — alguns trechos podem ter sido pulados)"
```
Nao e tratado como `visual_fallback`, nao esconde a recuperacao em chunks.

### Bateria real
Comando: `python -m tests.validate_pdf_public_batch --only=Posada,Cambio`
Artefatos:
- `C:\winegod-app\reports\pdf_batch_results_2026-04-10_1918.json`
- `C:\winegod-app\reports\pdf_batch_report_2026-04-10_1918.md`

---

## Resultado Posada

- **URL completa**: `https://img1.wsimg.com/blobby/go/26c4a5d2-ee07-47ed-96e6-4a367449196b/Posada%20Wine%20List.pdf`
- **Tamanho**: 115,6 KB
- **Paginas (pdfplumber)**: 35
- **Chars extraidos**: 29.857
- **Wine-related**: True
- **status**: `timeout`
- **extraction_method**: `timeout`
- **wine_count**: 0
- **was_truncated**: -
- **pages_processed**: -
- **latencia**: 300,37s

### Log do branch
```
[process_pdf] native_text error: Unterminated string starting at: line 2132 column 15 (char 48981)
[process_pdf] trying native_text_chunked recovery
status=timeout | latency=300.37s
```

**O chunked recovery FOI acionado**, mas o timeout de 300s foi atingido **antes de qualquer chunk completar**. Nao ha nenhum log `[chunked] chunk N/M` no output — o primeiro chunk ainda estava aguardando resposta do Gemini quando o timeout total estourou.

### Avaliacao curta
- Util? **Nao** — usuario nao recebe nada.
- Inventou item? Nao se aplica (zero itens).
- Preco grotescamente errado? Nao se aplica.
- Branch fez sentido? **Sim** — a logica do recovery foi acionada corretamente. O problema e latencia cumulativa: native_text falho (~150s gerando JSON quebrado) + chunked com chamadas Gemini de 60-150s cada nao cabe em 300s.

**Veredicto Posada: Reprovado novamente. A P3A.1 acionou o recovery mas nao concluiu antes do timeout.**

---

## Resultado Cambio de Tercio

- **URL completa**: `https://zangohosting.com/restaurant/wp-content/uploads/2023/02/604792-9190794c4873cda2a4ea7f351e15a225030bb3.pdf`
- **Tamanho**: 880,4 KB
- **Paginas (pdfplumber)**: 28
- **Chars extraidos**: 24.020
- **Wine-related**: True
- **status**: `success`
- **extraction_method**: `native_text` (NAO foi para chunked recovery nesta execucao)
- **wine_count**: 306 (apos dedup, de 334 retornados pelo Gemini)
- **was_truncated**: False
- **pages_processed**: 20
- **latencia**: 265,9s

### Log do branch
```
[process_pdf] native_text: 334 wines
status=success | method=native_text | wines=306 | pages=20
```

### Amostra de itens (10)
1. Reserva de la familia | Juve & Camps | macabeo, parellada, xarelo | £10.25
2. Fino Perdido | Palomino | £7.40
3. Manzanilla Alegria | Palomino | £7.25
4. Amontillado W&H 12 years old | W&H | Palomino | £8.00
5. Oloroso W&H 12 years old | W&H | Palomino | £8.00
6. Palo Cortado | Palomino | £8.00
7. La Malvar | malvar | V.T. CASTILLA | 2021 | £55.00
8. Don Quintin | viura, malvasia | D.O. RIOJA | 2020 | £55.00
9. Mas D'en Compte | garnacha, picapoll, xarel lo, macabeo | D.O. PRIORAT | 2017 | £71.00
10. As Sortes | godello | D.O. Valdeorras | 2020

### Avaliacao curta
- Util? **Sim** — 306 vinhos legitimos com regiao, uvas, safra, produtor.
- Inventou item? **Nao** — todos sao vinhos espanhois reais (Juve & Camps, Mas D'en Compte, As Sortes, etc.) coerentes com o restaurante londrino especializado em Espanha.
- Preco grotescamente errado? **Nao** — precos em £ (libras esterlinas) consistentes (£7-£127), coerentes com taca/garrafa de vinho fino em Londres.
- Branch fez sentido? **Sim** — native_text retornou JSON valido nesta tentativa. **Nao precisou do chunked recovery**.

**Veredicto Cambio: Aprovado com ressalva (latencia 266s e alta).**

**Observacao critica**: na bateria anterior (2026-04-10 18:22) este mesmo PDF reprovou com `Expecting property name enclosed in double quotes: line 2596 column 30`. Agora passou direto. Isso **confirma que o erro JSON do Gemini e nao-deterministico** — o mesmo input pode produzir JSON valido ou invalido em chamadas diferentes.

---

## Gap restante

### Posada continua reprovado
A P3A.1 implementou o recovery correto, mas o gargalo se moveu de **erro de parse** para **latencia cumulativa**:

| Componente | Tempo aproximado |
|---|---|
| Native_text inicial (Gemini gera 49K+ chars de JSON quebrado antes de raise) | ~150s |
| Primeiro chunk de recovery (8K chars de Posada) | >150s (ainda rodando no timeout) |
| **Total antes do timeout** | **300s** (cap) |

Para Posada concluir, e necessario um destes 3 caminhos (todos **fora do escopo desta P3A.1**):
1. **Paralelizar os chunks** (`concurrent.futures` dentro do worker) — 4 chamadas em paralelo terminariam em ~150s
2. **Reduzir chunk_size para ~4000 chars** — chunks menores devem voltar mais rapido individualmente
3. **Trocar modelo** (`gemini-2.0-flash` ou `gemini-1.5-flash`) — mais rapido e menos thinking-time
4. **Aumentar o timeout do worker** acima de 300s — soluciona Posada mas degrada UX

### Cambio passou por sorte de RNG
- Funcionou no native_text **sem usar** o chunked recovery
- A mesma URL falhou no run anterior (~3 horas atras)
- O fix nao foi exercitado neste caso — Cambio passou pelo caminho original
- **Nao podemos afirmar que a P3A.1 "consertou Cambio"** — Cambio passou porque o Gemini retornou JSON valido por sorte

### Latencia continua alta (achado nao novo)
- Cambio: 265,9s (proximo do timeout)
- Posada: estouraria mesmo se chunked funcionasse, pelo motivo acima
- UX de chat ao vivo continua inviavel para PDFs >20 paginas

### La Sirena (94 paginas)
**NAO HOMOLOGADO por bloqueio externo.** Servidor `lasirenaonline.com` retorna **HTTP 403 Forbidden** para downloads programaticos (mesmo com User-Agent de browser). Nao tentei workaround (proxy, headless browser) porque foge do escopo da P3A.1 e seria contornar uma protecao deliberada do servidor.

---

## Julgamento final

**A P3A.1 resolveu apenas 1 dos 2 casos, e por motivos diferentes:**

| PDF | Status anterior | Status atual | Atribuicao |
|---|---|---|---|
| Posada | Reprovado (parse fail → visual timeout) | **Reprovado** (parse fail → chunked timeout) | P3A.1 acionada mas insuficiente |
| Cambio de Tercio | Reprovado (parse fail → visual timeout) | **Aprovado** | Sucesso por nao-determinismo do Gemini, NAO pela P3A.1 |

### A frente de PDF esta pronta?

**Nao para PDFs longos (>25K chars / >20 paginas).** A P3A.1 e um passo correto na direcao certa, mas o bottleneck real e a **latencia da API Gemini para textos longos**, nao mais o erro de parse JSON. O patch:

- **Esta correto em design** (chunked recovery foi acionado quando necessario, branch isolada, regressao limpa)
- **E suficiente** para PDFs medios onde o JSON falha mas os chunks individuais cabem em 60-100s
- **Nao e suficiente** para PDFs muito longos onde mesmo os chunks individuais sao lentos demais

### O que a P3A.1 efetivamente entregou
1. Helper `_split_text_into_chunks` testado
2. Helper `_extract_wines_native_chunked` testado
3. Branch 1.5 com flag `native_text_failed` ativando chunked recovery em condicao especifica
4. Mapeamento explicito do novo metodo em `chat.py` com nota honesta
5. 10 testes novos (zero regressao)
6. Re-homologacao real publica (artefatos JSON+MD em reports)

### O que nao foi resolvido
- Posada continua reprovado
- Latencia geral ainda inaceitavel para UX de chat
- Nao-determinismo do Gemini ainda exposto

### Recomendacao
**Encerrar a P3A.1 aqui.** O fix esta deployavel (zero regressao, ganho liquido para PDFs medios) mas Posada precisa de uma **P3A.2** focada especificamente em **latencia**: paralelizacao de chunks ou troca de modelo. Nao misturar com P3A.1.

La Sirena fica registrado como **NAO HOMOLOGADO por bloqueio externo** — nao e bug do pipeline.
