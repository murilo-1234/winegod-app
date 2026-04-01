"""
Driver para Claude.ai (claude.ai) — Wine Classifier.
Adaptado do agent_discovery. Modelo: Opus 4.5.

Seletores copiados do discovery driver (2026-03-17).
"""

import time
from .base_driver import BaseDriver, set_clipboard, log


class ClaudeDriver(BaseDriver):
    name = "claude"
    url = "https://claude.ai/new"

    TIMEOUT_SEC = 420      # 7 min max (Opus pode demorar)
    STABLE_SEC = 30        # texto estavel 30s = completo
    MIN_WAIT_SEC = 120     # 2 min minimo antes de checar estabilidade

    INPUT_SELECTORS = [
        "[data-testid='chat-input']",
        "div.ProseMirror[contenteditable='true']",
        "[contenteditable='true'][data-placeholder]",
        "div[contenteditable='true']",
    ]

    SEND_SELECTORS = [
        "button[aria-label*='Send' i]",
        "button[aria-label*='Enviar' i]",
        "button[data-testid='send-button']",
    ]

    RESPONSE_SELECTORS = [
        "[data-is-streaming] .font-claude-response",
        ".font-claude-response",
        ".font-claude-response-body",
        "[data-is-streaming='false']",
        ".font-claude-message",
    ]

    LOADING_SELECTORS = [
        "[data-is-streaming='true']",
        "button[aria-label*='Stop' i]",
        ".animate-pulse",
    ]

    NEW_CHAT_SELECTORS = [
        "a[href='/new']",
        "button[aria-label*='New' i]",
        "a[data-testid='new-chat']",
    ]

    LOGIN_INDICATORS = [
        "button:has-text('Log in')",
        "button:has-text('Sign in')",
        "input[name='email']",
    ]

    def abrir_novo_chat(self, page):
        """Claude.ai: navegar para /new abre novo chat."""
        log(f"[{self.name}] Abrindo {self.url}")
        try:
            page.goto(self.url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log(f"[{self.name}] [ERRO] Falha ao abrir: {e}")
            return False

        time.sleep(5)

        bloqueio = self.detectar_bloqueio(page)
        if bloqueio == "sessao_expirada":
            log(f"[{self.name}] Sessao expirada detectada")
            return False

        self._selecionar_opus(page)

        log(f"[{self.name}] Chat pronto (Opus 4.5)")
        return True

    def _selecionar_opus(self, page):
        """Seleciona modelo Opus 4.5 no dropdown."""
        try:
            # Clicar no seletor de modelo
            model_selectors = [
                "button[data-testid='model-selector-dropdown']",
                "button[data-testid='model-selector']",
                "button:has-text('Sonnet')",
                "button:has-text('Opus')",
                "button:has-text('Claude')",
                "[aria-label*='model' i]",
            ]
            for sel in model_selectors:
                try:
                    btn = page.locator(sel)
                    if btn.count() > 0 and btn.first.is_visible(timeout=3000):
                        btn.first.click()
                        time.sleep(1)
                        break
                except Exception:
                    continue
            else:
                log(f"[{self.name}] Seletor de modelo nao encontrado — usando padrao")
                return

            # Selecionar Opus
            opus_selectors = [
                "div:has-text('Opus'):not(:has(div))",
                "[data-testid='model-option-opus']",
                "button:has-text('Opus')",
                "li:has-text('Opus')",
                "[role='option']:has-text('Opus')",
                "[role='menuitem']:has-text('Opus')",
            ]
            for sel in opus_selectors:
                try:
                    opt = page.locator(sel)
                    if opt.count() > 0:
                        opt.first.click()
                        time.sleep(1)
                        log(f"[{self.name}] Modelo Opus 4.5 selecionado")
                        return
                except Exception:
                    continue

            log(f"[{self.name}] [AVISO] Nao conseguiu selecionar Opus — verificar manualmente")
        except Exception as e:
            log(f"[{self.name}] [AVISO] Erro ao selecionar modelo: {e}")

    def colar_mensagem(self, page, texto):
        """Claude.ai: colar via JS focus + execCommand para textos grandes.

        Claude converte Ctrl+V de textos >5K em attachment "PASTED".
        Para evitar, usa execCommand('insertText') direto.
        """
        # Focar editor via JS (bypass actionability checks)
        focused = page.evaluate("""() => {
            const selectors = [
                '[data-testid="chat-input"]',
                'div.ProseMirror[contenteditable="true"]',
                '[contenteditable="true"][data-placeholder]',
                'div[contenteditable="true"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    el.focus();
                    el.click();
                    return true;
                }
            }
            return false;
        }""")

        if not focused:
            raise Exception(f"[{self.name}] Campo de input nao encontrado")

        time.sleep(0.3)
        page.keyboard.press("Control+a")
        time.sleep(0.1)
        page.keyboard.press("Backspace")
        time.sleep(0.2)

        if len(texto) > 5000:
            # Inserir via JS execCommand — evita attachment "PASTED"
            page.evaluate("""(text) => {
                const el = document.querySelector('[data-testid="chat-input"]')
                    || document.querySelector('div.ProseMirror[contenteditable="true"]');
                if (!el) return;
                el.focus();
                document.execCommand('insertText', false, text);
            }""", texto)
            wait = 5.0 if len(texto) > 10000 else 3.0
            time.sleep(wait)

            # Verificar se texto foi inserido
            try:
                input_len = page.evaluate("""() => {
                    const el = document.querySelector('[data-testid="chat-input"]')
                        || document.querySelector('div.ProseMirror[contenteditable="true"]');
                    return el ? el.innerText.length : 0;
                }""")
                if input_len < len(texto) * 0.3:
                    log(f"[{self.name}] [AVISO] insertText parcial ({input_len}/{len(texto)}), retry clipboard...")
                    set_clipboard(texto)
                    time.sleep(0.5)
                    page.keyboard.press("Control+v")
                    time.sleep(wait)
            except Exception as e:
                log(f"[{self.name}] [AVISO] Verificacao pos-insert: {e}")
        else:
            set_clipboard(texto)
            time.sleep(0.5)
            page.keyboard.press("Control+v")
            time.sleep(2.0)

        log(f"[{self.name}] Texto colado ({len(texto)} chars)")

    def enviar_mensagem(self, page):
        """Claude.ai: Enter envia a mensagem."""
        time.sleep(0.5)

        for sel in self.SEND_SELECTORS:
            try:
                btn = page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible(timeout=2000):
                    btn.first.click()
                    log(f"[{self.name}] Enviado via botao")
                    return True
            except Exception:
                continue

        page.keyboard.press("Enter")
        log(f"[{self.name}] Enviado via Enter")
        return True
