# Handoff — Operacao Codex Wine Classifier

Voce ja leu o PROMPT_CTO_WINEGOD_V2.md e conhece o projeto. Este handoff e especifico sobre a operacao do Codex que estamos fazendo AGORA.

## O que estamos fazendo

Estamos usando o Codex (OpenAI, plano Plus, NAO API) para classificar vinhos de lojas em paralelo com os navegadores (Mistral, Grok, GLM, etc). O Codex le arquivos com 1000 nomes de produtos, classifica cada um como vinho (W), nao-vinho (X) ou destilado (S), e salva num arquivo de resposta. Depois um script Python insere no banco.

## Estado atual

### Abas pendentes da rodada R6
- **Aba 12** (lotes r_0975 a r_0999): 0/25 prontos — NAO FOI EXECUTADA
- **Aba 13** (lotes r_1000 a r_1024): 12/25 prontos — INCOMPLETA

Para remandar:
```
Aba 12: REGRA ABSOLUTA: NAO crie arquivos .py .ps1 .js .bat. NAO copie de outros arquivos. Leia C:/winegod-app/prompts/PROMPT_CODEX_V2_R6_ABA_12.md e siga as instrucoes. NAO pare entre lotes.

Aba 13: REGRA ABSOLUTA: NAO crie arquivos .py .ps1 .js .bat. NAO copie de outros arquivos. Leia C:/winegod-app/prompts/PROMPT_CODEX_V2_R6_ABA_13.md e siga as instrucoes. NAO pare entre lotes.
```

### Itens pendentes no pipeline (2.09M total)

| Letra | Pendentes | Quem cobre |
|---|---|---|
| C | 413K | Mistral (Chrome 1) + Codex pode ajudar |
| B | 218K | Mistral + Codex |
| D | 195K | Mistral + Codex |
| M | 188K | Chrome 3 (ChatGPT+Gemini) + Codex |
| L | 167K | Mistral + Codex |
| A | 155K | Mistral + Codex |
| G | 118K | Mistral + Codex |
| F | 103K | Mistral + Codex |
| S | 101K | Edge + Codex |
| E | 77K | Mistral + Codex |
| H | 65K | Mistral + Codex |
| K | 61K | Mistral + Codex |
| W | 57K | Edge + Codex |
| J, N | 52K cada | Mistral/Chrome3 + Codex |
| I, Y | 30K/12K | Mistral/Edge + Codex |
| T, V, Z | 8K/4K/3K | Codex (quase prontos) |
| O, P, Q, R | 0 | Ja completos |

O Codex NAO tem restricao de letra — a query pega qualquer pendente. Os navegadores sao restritos por letra (Mistral=0-9,A-L / Chrome3=M-N / Edge=O,P,Q,R,S,W,Y). O Codex complementa.

## Como gerar prompts — PASSO A PASSO

### 1. Gerar lotes

```bash
cd C:\winegod-app
python scripts/gerar_lotes_codex.py 150   # 150 lotes de 1000
```

Isso gera arquivos em `lotes_codex/`:
- `lote_r_NNNN.txt` — prompt B v2 + 1000 itens numerados
- `lote_r_NNNN_ids.txt` — 1000 clean_ids (vinculam resposta ao banco)

A query pega pendentes em ordem Z→A (nao conflita com navegadores que vao A→Z).

### 2. Gerar prompts por aba

Cada prompt combina:
- O **PROMPT_CODEX_BASE_V2.md** (regras de classificacao, exemplos de produtor)
- Lista de 10 lotes especificos com caminhos dos arquivos

Estrutura:
```
[conteudo do PROMPT_CODEX_BASE_V2.md sem a secao FACA EM BLOCOS]

## FACA EM BLOCOS DE 250

### LOTE 1 (lote_r_0700)
1. Leia C:/winegod-app/lotes_codex/lote_r_0700.txt
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_0700.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 2 (lote_r_0701)
...

## COMECE AGORA. NAO PARE ATE TERMINAR TODOS OS 10 LOTES.
```

**CAPACIDADE:** 10 lotes por aba funciona bem. 25 funciona mas ~20% das abas falham. NAO use mais que 25.

### 3. Colar nas abas do Codex

Abrir ate 15 abas simultaneas. Em cada uma, colar:

```
REGRA ABSOLUTA: NAO crie arquivos .py .ps1 .js .bat. NAO copie de outros arquivos. Leia C:/winegod-app/prompts/PROMPT_CODEX_V2_R6_ABA_N.md e siga as instrucoes. NAO pare entre lotes.
```

### 4. Salvar no banco

```bash
python scripts/salvar_respostas_codex.py              # salva TODOS pendentes
python scripts/salvar_respostas_codex.py 700 701 702  # salva especificos
```

### 5. Verificar qualidade

```bash
python -c "
lines = open('lotes_codex/resposta_r_0700.txt').readlines()
w = sum(1 for l in lines if 'W|' in l)
print(f'{len(lines)} linhas, {w} vinhos')
"
```

## O prompt PROMPT_CODEX_BASE_V2.md — POR QUE ESTE E NAO OUTRO

### Historico de erros e correcoes

1. **Prompt V1 (simples):** O Codex deixava 73% dos vinhos SEM produtor. Motivo: nenhum exemplo de como separar produtor/vinho. Resultado: 94K vinhos inuteis pro match Vivino.

2. **Codex cria scripts:** O Codex e um agente de CODIGO. Quando pedimos "classifique vinhos", ele escreve um script PowerShell com if/else em vez de usar seu conhecimento. Solucao: "REGRA ABSOLUTA: NAO crie .py .ps1" como PRIMEIRA frase.

3. **Codex copia respostas:** Se existem arquivos resposta_*.txt na pasta, o Codex copia em vez de classificar. Solucao: "NAO copie de outros arquivos" + mover respostas prontas se necessario.

4. **Duplicatas excessivas (45%):** O Codex marcava vinhos de safras diferentes como duplicata. Solucao: "Safra diferente = NAO e duplicata" explicito no prompt.

### O que o prompt V2 tem de especial

- **9 exemplos concretos de produtor/vinho** — o campo mais critico
- **"NUNCA deixe ?? no produtor"** — forcado, nao opcional
- **"O produtor e geralmente a PRIMEIRA parte do nome"** — regra pratica
- **Lista expandida de uvas por cor** — evita pinot gris como tinto
- **Blocos de 250** — o Codex nao aguenta 1000 de uma vez
- **Anti-script e anti-copia** — as duas primeiras secoes do prompt

### Metricas comprovadas (prompt V2)

| Campo | Taxa |
|---|---|
| Produtor | 99-100% |
| Vinho | 99-100% |
| Safra | 100% |
| Cor | 83-92% |
| Corpo | 83-87% |
| Pais | 17-93% (varia) |
| Harmonizacao | 72-90% |
| ABV | 69-90% |

## Arquivos importantes

| Arquivo | O que e |
|---|---|
| `prompts/PROMPT_CODEX_BASE_V2.md` | Prompt base com exemplos de produtor (USAR ESTE) |
| `prompts/PROMPT_CODEX_V2_R6_ABA_*.md` | Prompts por aba da rodada 6 |
| `prompts/CORRECAO_PROMPT_CODEX.md` | Documentacao do bug do produtor vazio |
| `scripts/gerar_lotes_codex.py` | Gera lotes de 1000 |
| `scripts/salvar_respostas_codex.py` | Salva respostas no banco |
| `lotes_codex/` | Pasta com lotes (input) e respostas (output) |

## Proximos passos

1. Remandar abas 12 e 13 da R6 (38K itens)
2. Gerar nova rodada: 15 abas × 10 lotes = 150K itens (letras maiores: C, B, D, M, L)
3. Salvar e repetir ate zerar os 2.09M pendentes
4. Com 15 abas fazendo 150K por rodada, sao ~14 rodadas pra terminar tudo
