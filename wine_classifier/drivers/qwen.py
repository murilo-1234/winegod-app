"""
Driver para Qwen (chat.qwen.ai) — com Thinking mode.
Copiado do Discovery.
"""

import time
from .base_driver import BaseDriver, log


class QwenDriver(BaseDriver):
    name = "qwen"
    url = "https://chat.qwen.ai"

    TIMEOUT_SEC = 420
    STABLE_SEC = 30
    MIN_WAIT_SEC = 180

    INPUT_SELECTORS = [
        "textarea.message-input-textarea",
        "textarea[placeholder*='How can I help']",
        "textarea[placeholder]",
        ".message-input-textarea",
        "textarea",
    ]

    SEND_SELECTORS = [
        ".omni-button-content-btn",
        "button.ant-btn-primary.ant-btn-circle",
        ".message-input-right-button-send button",
        "button[type='button'].ant-btn-primary",
    ]

    RESPONSE_SELECTORS = [
        ".markdown-body",
        "div[class*='markdown']",
        "[class*='message-content']",
        "[class*='assistant'] [class*='content']",
        "[class*='answer']",
        "[class*='response']",
        "[class*='reply']",
    ]

    LOADING_SELECTORS = [
        "[class*='loading']",
        "[class*='generating']",
        "[class*='typing']",
        "[class*='stop']",
        "button[aria-label*='Stop' i]",
    ]

    NEW_CHAT_SELECTORS = [
        "[class*='new-chat']",
        "[class*='newChat']",
        "a[href='/']",
        "button[aria-label*='New' i]",
    ]

    LOGIN_INDICATORS = [
        "input[type='email']",
        "input[type='phone']",
        "button[class*='login']",
        "[class*='login-container']",
        "[class*='sign-in']",
    ]

    def abrir_novo_chat(self, page):
        log(f"[{self.name}] Abrindo {self.url}")
        try:
            page.goto(self.url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log(f"[{self.name}] [ERRO] Falha ao abrir: {e}")
            return False

        time.sleep(5)

        bloqueio = self.detectar_bloqueio(page)
        if bloqueio == "sessao_expirada":
            log(f"[{self.name}] Sessao expirada - pulando")
            return False

        for sel in self.NEW_CHAT_SELECTORS:
            try:
                btn = page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible(timeout=3000):
                    btn.first.click()
                    time.sleep(2)
                    log(f"[{self.name}] Novo chat via botao")
                    return True
            except Exception:
                continue

        log(f"[{self.name}] Chat pronto (automatico)")
        return True

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
