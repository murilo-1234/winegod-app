# Metodo Linguas

Diretorio canonico do metodo oficial de rollout i18n do WineGod.

Ponto de entrada:

- `COMECE_AQUI.md`

Arquivos principais:

- `WINEGOD_MULTILINGUE_METODO_BASE_OFICIAL.md`
- `WINEGOD_MULTILINGUE_METODO_RESUMO_EXECUTIVO.md`
- `WINEGOD_MULTILINGUE_METODO_GAPS_E_PENDENCIAS.md`
- `WINEGOD_MULTILINGUE_TEMPLATE_JOB_NOVO_LOCALE.md`
- `WINEGOD_MULTILINGUE_TEMPLATE_DECISIONS_NOVO_LOCALE.md`
- `WINEGOD_MULTILINGUE_TEMPLATE_RESULTADO_NOVO_LOCALE.md`
- `WINEGOD_MULTILINGUE_TEMPLATE_HANDOFF_FINAL_NOVO_LOCALE.md`

Regra de uso:

- `docs/metodo-linguas/` = sistema canonico e templates reutilizaveis
- `reports/` = execucao historica de cada locale, resultados, handoffs e log append-only

Fluxo:

1. Ler `WINEGOD_MULTILINGUE_METODO_RESUMO_EXECUTIVO.md`
2. Usar `WINEGOD_MULTILINGUE_METODO_BASE_OFICIAL.md` como regra mestre
3. Copiar os templates para `reports/` com o nome do job novo
4. Registrar execucao em `reports/i18n_execution_log.md`
