// ESLint flat config - F0.5 bootstrap + F3.1 i18n guard (warn only).
// Compatible with ESLint 9 + Next 15.
// F3.1: ativa `i18next/no-literal-string` apenas em app/**/*.tsx e
// components/**/*.tsx, em severity `warn`. Nao toca lib/, i18n/, messages/,
// middleware.ts, next.config.ts ou qualquer .ts puro fora de componentes.
// Ainda nao temos baseline (F3.2) nem GH Action (F3.3).

import nextPlugin from "@next/eslint-plugin-next";
import reactPlugin from "eslint-plugin-react";
import reactHooksPlugin from "eslint-plugin-react-hooks";
import i18nextPlugin from "eslint-plugin-i18next";
import tseslint from "typescript-eslint";

export default [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      "tsconfig.tsbuildinfo",
      "public/**",
    ],
  },
  {
    files: [
      "app/**/*.{js,jsx,ts,tsx}",
      "components/**/*.{js,jsx,ts,tsx}",
      "lib/**/*.{js,jsx,ts,tsx}",
      "types/**/*.{js,jsx,ts,tsx}",
    ],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        window: "readonly",
        document: "readonly",
        console: "readonly",
        process: "readonly",
        fetch: "readonly",
        localStorage: "readonly",
        sessionStorage: "readonly",
        navigator: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        HTMLElement: "readonly",
        HTMLInputElement: "readonly",
        HTMLTextAreaElement: "readonly",
        HTMLDivElement: "readonly",
        Element: "readonly",
        Event: "readonly",
        MouseEvent: "readonly",
        KeyboardEvent: "readonly",
        FormData: "readonly",
        File: "readonly",
        Blob: "readonly",
        FileReader: "readonly",
        AbortController: "readonly",
        Request: "readonly",
        Response: "readonly",
        Headers: "readonly",
        WebSocket: "readonly",
      },
    },
    plugins: {
      "@next/next": nextPlugin,
      react: reactPlugin,
      "react-hooks": reactHooksPlugin,
      "@typescript-eslint": tseslint.plugin,
    },
    settings: {
      react: { version: "detect" },
    },
    rules: {
      // Keep it pragmatic in F0.5: lint runs without wizard, no warning is
      // promoted to an error. F3.1 ativou a guard em bloco dedicado abaixo.
      ...nextPlugin.configs.recommended.rules,
    },
  },
  // F3.1 - i18n guard restrita a rotas e componentes visuais. Qualquer TS
  // puro, lib/, i18n/, messages/, middleware.ts, next.config.ts etc. ficam
  // FORA: este bloco so matcha .tsx em app/ e components/.
  {
    files: ["app/**/*.tsx", "components/**/*.tsx"],
    plugins: {
      i18next: i18nextPlugin,
    },
    rules: {
      "i18next/no-literal-string": [
        "error",
        {
          // F3.1 original: so inspeciona texto JSX (equivalente a markupOnly).
          // F4.19: promovido para "error" apos zerar warnings.
          mode: "jsx-text-only",
          "jsx-attributes": {
            exclude: [
              "aria-label",
              "aria-labelledby",
              "aria-describedby",
              "aria-valuetext",
              "data-testid",
              "className",
              "role",
              "type",
              "name",
              "id",
              "href",
              "src",
            ],
          },
          callees: {
            exclude: [
              "console.log",
              "console.warn",
              "console.error",
              "console.info",
              "console.debug",
              "JSON.parse",
              "JSON.stringify",
            ],
          },
          words: {
            // Defaults do plugin + allowlist custom. O plugin prepende
            // "(^|\\.)" em cada regex e appenda "$" quando ausente.
            exclude: [
              // defaults do plugin (preservar):
              "[0-9!-/:-@[-`{-~]+",
              "[A-Z_-]+",
              // F4.19 - brand e fragmentos de brand (nao traduziveis)
              "winegod\\.ai",
              "winegod",
              "\\.ai",
              // F4.19 - icones textuais (close "x", "X", "×")
              "[xX\\u00D7]",
              // F4.19 - estrelas e simbolos de rating (entities decodificadas
              // pelo JSX parser viram os chars unicode diretos, ex: &#9733; -> ★)
              "[\\u2605\\u2606\\u2B50]",
              // F4.19 - HTML numeric entities quando aparecem cruas em source
              "&#\\d+;",
            ],
          },
          message:
            "[i18n] Strings de UI devem ser resolvidas via next-intl (t('chave')).",
        },
      ],
    },
  },
];
