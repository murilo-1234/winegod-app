"""
Driver para Gemini (gemini.google.com) — modo RAPIDO.
Fork do Discovery gemini.py — seleciona Rapido em vez de Raciocinio.
"""

import time
from .base_driver import BaseDriver, log


class GeminiRapidoDriver(BaseDriver):
    name = "gemini"
    url = "https://gemini.google.com/app"

    INPUT_SELECTORS = [
        ".ql-editor[contenteditable='true']",
        "rich-textarea div[contenteditable='true']",
        "div.input-area [contenteditable='true']",
        "[contenteditable='true'][aria-label*='prompt' i]",
        "[contenteditable='true'][aria-label*='Enter' i]",
        "[contenteditable='true'][aria-label*='message' i]",
        "div[contenteditable='true']",
    ]

    SEND_SELECTORS = [
        "button[aria-label*='Send' i]",
        "button[aria-label*='Enviar' i]",
        "button.send-button",
        ".send-button-container button",
        "button[mattooltip*='Send' i]",
    ]

    RESPONSE_SELECTORS = [
        ".model-response-text .markdown",
        ".model-response-text",
        ".response-container .markdown",
        "model-response .markdown",
        "message-content.model-response-text",
        "[data-message-author='1']",
    ]

    LOADING_SELECTORS = [
        "button[aria-label*='Stop' i]",
        ".loading-indicator",
        ".thinking-indicator",
        "mat-progress-bar",
        ".generating-response",
    ]

    NEW_CHAT_SELECTORS = [
        "button[aria-label*='New chat' i]",
        "button[aria-label*='Nova conversa' i]",
        "a[href='/app']",
        ".new-chat-button",
    ]

    LOGIN_INDICATORS = [
        "input[type='email'][name='identifier']",
        "#identifierId",
        "[data-identifier='signIn']",
    ]

    def abrir_novo_chat(self, page):
        """Gemini: navegar para /app + selecionar modo Rapido."""
        log(f"[{self.name}] Abrindo {self.url}")
        page.goto(self.url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)

        bloqueio = self.detectar_bloqueio(page)
        if bloqueio == "sessao_expirada":
            log(f"[{self.name}] Sessao expirada detectada")
            return False

        # Tentar clicar "New chat"
        for sel in self.NEW_CHAT_SELECTORS:
            try:
                btn = page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible(timeout=3000):
                    btn.first.click()
                    time.sleep(2)
                    log(f"[{self.name}] Novo chat via botao")
                    break
            except Exception:
                continue

        # Garantir modo RAPIDO (nao Raciocinio)
        self._selecionar_rapido(page)

        log(f"[{self.name}] Chat pronto (modo Rapido)")
        return True

    def _selecionar_rapido(self, page):
        """Seleciona modo Rapido no Gemini. Se ja esta em Rapido, nao faz nada."""
        try:
            mode_btn = page.locator("button[aria-label='Abrir seletor de modo']")
            if mode_btn.count() > 0 and mode_btn.first.is_visible(timeout=3000):
                btn_text = mode_btn.first.inner_text(timeout=2000)

                # Ja esta em Rapido?
                if "Rápido" in btn_text or "Fast" in btn_text:
                    log(f"[{self.name}] Modo Rapido ja ativo")
                    return True

                # Abrir seletor e escolher Rapido
                mode_btn.first.click()
                time.sleep(1)

                rapido_opt = page.locator(
                    "button:has-text('Rápido'), button:has-text('Fast'), "
                    "[role='option']:has-text('Rápido'), [role='menuitem']:has-text('Rápido'), "
                    "[role='option']:has-text('Fast'), [role='menuitem']:has-text('Fast')"
                )
                if rapido_opt.count() > 0:
                    rapido_opt.first.click()
                    time.sleep(1)
                    log(f"[{self.name}] Modo Rapido selecionado")
                    return True
                else:
                    page.keyboard.press("Escape")
                    log(f"[{self.name}] [AVISO] Opcao Rapido nao encontrada")
            else:
                log(f"[{self.name}] Seletor de modo nao encontrado — usando padrao")
        except Exception as e:
            log(f"[{self.name}] [AVISO] Erro ao selecionar Rapido: {e}")
        return False

    def enviar_mensagem(self, page):
        """Gemini: botao Send primeiro, depois Enter."""
        time.sleep(0.5)

        for sel in self.SEND_SELECTORS:
            try:
                btn = page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible(timeout=3000):
                    btn.first.click()
                    log(f"[{self.name}] Enviado via botao Send")
                    return True
            except Exception:
                continue

        page.keyboard.press("Enter")
        log(f"[{self.name}] Enviado via Enter (fallback)")
        return True
