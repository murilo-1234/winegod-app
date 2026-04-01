"""
Driver para ChatGPT (chatgpt.com).
Copiado do Discovery. Sem thinking mode. SPLIT_PROMPT desabilitado.
"""

import time
from .base_driver import BaseDriver, set_clipboard, log


class ChatGPTDriver(BaseDriver):
    name = "chatgpt"
    url = "https://chatgpt.com"

    INPUT_SELECTORS = [
        "#prompt-textarea",
        "div#prompt-textarea",
        "div[contenteditable='true'][data-placeholder]",
        "textarea[data-id='root']",
        "div[contenteditable='true']",
    ]

    SEND_SELECTORS = [
        "button[data-testid='send-button']",
        "button[aria-label*='Send' i]",
        "button[aria-label*='Enviar' i]",
        "form button[type='submit']",
    ]

    RESPONSE_SELECTORS = [
        "[data-message-author-role='assistant'] .markdown",
        ".agent-turn .markdown",
        "[data-message-author-role='assistant']",
        ".group\\/conversation-turn .markdown",
    ]

    LOADING_SELECTORS = [
        "button[aria-label*='Stop' i]",
        "button[data-testid='stop-button']",
        ".result-streaming",
    ]

    NEW_CHAT_SELECTORS = [
        "a[href='/']",
        "button[aria-label*='New chat' i]",
        "nav a[href='/']",
    ]

    LOGIN_INDICATORS = [
        "button[data-testid='login-button']",
        "input[name='username']",
        "[data-testid='login-page']",
    ]

    def abrir_novo_chat(self, page):
        log(f"[{self.name}] Abrindo {self.url}")
        page.goto(self.url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)

        bloqueio = self.detectar_bloqueio(page)
        if bloqueio == "sessao_expirada":
            log(f"[{self.name}] Sessao expirada detectada")
            return False

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

        log(f"[{self.name}] Chat pronto")
        return True

    def colar_mensagem(self, page, texto):
        """ChatGPT: override para contenteditable #prompt-textarea."""
        input_el = self._find_input(page)
        if not input_el:
            raise Exception(f"[{self.name}] Campo de input nao encontrado")

        input_el.click()
        time.sleep(0.3)
        page.keyboard.press("Control+a")
        time.sleep(0.1)
        page.keyboard.press("Backspace")
        time.sleep(0.2)

        set_clipboard(texto)
        time.sleep(0.3)
        page.keyboard.press("Control+v")

        wait = 1.0
        if len(texto) > 10000:
            wait = 4.0
        elif len(texto) > 5000:
            wait = 2.5
        time.sleep(wait)

        log(f"[{self.name}] Texto colado ({len(texto)} chars)")

    def enviar_mensagem(self, page):
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
