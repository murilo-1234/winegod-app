#!/usr/bin/env node
// H4 F2 - Valida parity estrutural entre frontend/messages/*.json.
//
// Gate primario determinista do H4 (DECISIONS 2026-04-22). Usar antes de
// commitar qualquer traducao de es-419.json ou fr-FR.json.
//
// Checks:
//  - mesma contagem de leaves (baseline = en-US).
//  - nenhuma chave MISSING ou EXTRA por locale.
//  - ICU placeholders ({name}, {age}, {count}, etc.) batem com baseline.
//  - rich tags (<a>, <b>, <terms>, <privacy>, <email>, etc.) batem.
//  - branches de plural (one/other/=0/zero/few/many/two) batem.
//  - heuristica leve: aviso (nao erro) para possivel vazamento de idioma.
//
// Exit 0 => OK. Exit 1 => divergencia estrutural bloqueante.

import fs from "node:fs";
import path from "node:path";
import url from "node:url";

const __filename = url.fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..");

const LOCALES = ["pt-BR", "en-US", "es-419", "fr-FR"];
const BASELINE = "en-US";
const MSG_DIR = path.join(REPO_ROOT, "frontend", "messages");

function flatten(obj, prefix = "") {
  const r = {};
  for (const k of Object.keys(obj)) {
    const v = obj[k];
    const kk = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v))
      Object.assign(r, flatten(v, kk));
    else r[kk] = v;
  }
  return r;
}

function extract(s) {
  if (typeof s !== "string") return { icu: [], tags: [], plurals: [] };
  // ICU placeholder real: `{name}` ou `{name, number/plural/select/...}`.
  // O `}` ou `, <keyword>` apos o nome distingue placeholder de branch
  // aninhado como `wed {Midweek, ...}` dentro de select.
  const icu = [
    ...s.matchAll(
      /\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\}|,\s*(?:number|plural|select|selectordinal|date|time)\b)/g,
    ),
  ].map((m) => m[1]);
  const tags = [...s.matchAll(/<([a-zA-Z_][a-zA-Z0-9_]*)>/g)].map((m) => m[1]);
  const plurals = [
    ...s.matchAll(/\b(one|other|zero|two|few|many|=0|=1|=2)\s*\{/g),
  ].map((m) => m[1]);
  return {
    icu: [...new Set(icu)].sort(),
    tags: [...new Set(tags)].sort(),
    plurals: [...new Set(plurals)].sort(),
  };
}

const load = (l) =>
  JSON.parse(fs.readFileSync(path.join(MSG_DIR, `${l}.json`), "utf8"));

const flat = Object.fromEntries(LOCALES.map((l) => [l, flatten(load(l))]));
const baseKeys = new Set(Object.keys(flat[BASELINE]));

// Heuristica leve de idioma vazando. So sinaliza palavras lexicamente
// distintivas (PT: você, não, são, crédito). Diacriticos compartilhados
// (á é í ó ú ê ç) entre romance languages NAO sao marcador confiavel.
const PT_MARKERS =
  /\b(voc[êê]|n[ãã]o|s[ãã]o|est[ãã]o|cr[eé]dito|mensagem|conversa|p[aá]gina|pr[oó]xim[oa]|obrigad[oa]|ap[oó]s|atraves|tamb[eé]m)\b/i;
const EN_MARKERS =
  /\b(you're|isn't|aren't|doesn't|don't|haven't|can't|won't|please\s+try|sign\s+in|log\s+in|learn\s+more|go\s+back|try\s+again|something\s+went\s+wrong|your\s+(account|plan|chat|wine|credits))\b/i;
const BRAND_EXEMPT = /winegod|chat\.winegod|@winegod|privacy@|legal/i;

let errors = 0;
let warnings = 0;
const report = [];

for (const locale of LOCALES) {
  const keys = new Set(Object.keys(flat[locale]));
  const leaves = keys.size;
  const missing = [...baseKeys].filter((k) => !keys.has(k));
  const extra = [...keys].filter((k) => !baseKeys.has(k));

  report.push(`[${locale}] ${leaves} leaves`);

  if (missing.length) {
    errors++;
    report.push(
      `  MISSING (${missing.length}): ${missing.slice(0, 10).join(", ")}${missing.length > 10 ? "..." : ""}`,
    );
  }
  if (extra.length) {
    errors++;
    report.push(
      `  EXTRA (${extra.length}): ${extra.slice(0, 10).join(", ")}${extra.length > 10 ? "..." : ""}`,
    );
  }

  // Para cada chave presente em ambos, comparar placeholders/tags/plurals
  for (const k of baseKeys) {
    if (!keys.has(k)) continue;
    const pB = extract(flat[BASELINE][k]);
    const pL = extract(flat[locale][k]);
    if (JSON.stringify(pB.icu) !== JSON.stringify(pL.icu)) {
      errors++;
      report.push(
        `  ICU MISMATCH at "${k}": base=${JSON.stringify(pB.icu)} locale=${JSON.stringify(pL.icu)}`,
      );
    }
    if (JSON.stringify(pB.tags) !== JSON.stringify(pL.tags)) {
      errors++;
      report.push(
        `  TAGS MISMATCH at "${k}": base=${JSON.stringify(pB.tags)} locale=${JSON.stringify(pL.tags)}`,
      );
    }
    if (JSON.stringify(pB.plurals) !== JSON.stringify(pL.plurals)) {
      errors++;
      report.push(
        `  PLURAL MISMATCH at "${k}": base=${JSON.stringify(pB.plurals)} locale=${JSON.stringify(pL.plurals)}`,
      );
    }
  }

  // Heuristica de vazamento
  if (locale !== "pt-BR") {
    for (const [k, v] of Object.entries(flat[locale])) {
      if (typeof v !== "string") continue;
      if (BRAND_EXEMPT.test(v)) continue;
      if (PT_MARKERS.test(v)) {
        warnings++;
        report.push(
          `  WARN pt-BR leak? at "${k}": ${v.slice(0, 80).replace(/\n/g, " ")}`,
        );
      }
    }
  }
  if (locale !== "en-US" && locale !== "pt-BR") {
    for (const [k, v] of Object.entries(flat[locale])) {
      if (typeof v !== "string") continue;
      if (BRAND_EXEMPT.test(v)) continue;
      if (EN_MARKERS.test(v)) {
        warnings++;
        report.push(
          `  WARN en-US leak? at "${k}": ${v.slice(0, 80).replace(/\n/g, " ")}`,
        );
      }
    }
  }
}

console.log(report.join("\n"));
console.log("");
if (errors > 0) {
  console.error(`FAIL: ${errors} structural issues (${warnings} warnings)`);
  process.exit(1);
}
console.log(`OK: 4 locales with parity (${warnings} warnings to review)`);
