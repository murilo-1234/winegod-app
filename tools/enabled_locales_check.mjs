#!/usr/bin/env node
// H4 F5.3 (A6 do julgamento) - Valida consistencia entre a lista de
// locales habilitados do MIDDLEWARE estatico (NEXT_PUBLIC_ENABLED_LOCALES
// ou ENABLED_LOCALES em build time) e a lista dinamica do BACKEND
// (/api/config/enabled-locales, lida de feature_flags).
//
// Uso:
//   NEXT_PUBLIC_ENABLED_LOCALES='["pt-BR","en-US","es-419","fr-FR"]' \
//     API_BASE=https://winegod-app.onrender.com \
//     node tools/enabled_locales_check.mjs
//
// Exit 0 => ambas listas batem. Exit 1 => divergencia bloqueante.
// Defaults:
//   API_BASE = https://winegod-app.onrender.com
//   NEXT_PUBLIC_ENABLED_LOCALES = '["pt-BR","en-US","es-419","fr-FR"]'
//     (ou ENABLED_LOCALES)

const API_BASE = process.env.API_BASE || "https://winegod-app.onrender.com";
const staticRaw =
  process.env.NEXT_PUBLIC_ENABLED_LOCALES ||
  process.env.ENABLED_LOCALES ||
  '["pt-BR","en-US","es-419","fr-FR"]';

function parseList(raw) {
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed;
  } catch {
    // fallthrough para CSV
  }
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

const staticList = [...new Set(parseList(staticRaw))].sort();

let dynamicList;
try {
  const res = await fetch(`${API_BASE}/api/config/enabled-locales`);
  if (!res.ok) {
    console.error(`FAIL: HTTP ${res.status} from ${API_BASE}/api/config/enabled-locales`);
    process.exit(1);
  }
  const data = await res.json();
  if (!Array.isArray(data.enabled_locales)) {
    console.error("FAIL: payload missing enabled_locales array");
    console.error(JSON.stringify(data, null, 2));
    process.exit(1);
  }
  dynamicList = [...new Set(data.enabled_locales)].sort();
} catch (err) {
  console.error(`FAIL: cannot reach ${API_BASE}:`, err.message);
  process.exit(1);
}

console.log("static  (NEXT_PUBLIC_ENABLED_LOCALES):", JSON.stringify(staticList));
console.log("dynamic (/api/config/enabled-locales):", JSON.stringify(dynamicList));

if (JSON.stringify(staticList) !== JSON.stringify(dynamicList)) {
  console.error(
    "\nFAIL: mismatch. Rebuild frontend with correct NEXT_PUBLIC_ENABLED_LOCALES\n" +
      "OR update feature_flags.enabled_locales in the backend DB.",
  );
  process.exit(1);
}

console.log("\nOK: static and dynamic enabled_locales lists match.");
