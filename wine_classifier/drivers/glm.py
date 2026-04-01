"""
Driver para GLM 5 (chat.z.ai).
NOVO — seletores estimados, refinar apos teste manual via setup_edge.py.
"""

import time
from .base_driver import BaseDriver, log


class GLMDriver(BaseDriver):
    name = "glm"
    url = "https://chat.z.ai"

    TIMEOUT_SEC = 420
    STABLE_SEC = 30
    MIN_WAIT_SEC = 180

    # Seletores estimados — refinar via DevTools (F12)
    INPUT_SELECTORS = [
        "textarea",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
        "[contenteditable='true'][aria-label*='message' i]",
        "[class*='chat-input'] textarea",
        "[class*='input-area'] textarea",
    ]

    SEND_SELECTORS = [
        "button[type='submit']",
        "button[aria-label*='Send' i]",
        "button[aria-label*='send' i]",
        "button[class*='send']",
        "form button:last-of-type",
    ]

    RESPONSE_SELECTORS = [
        "div[class*='markdown']",
        "[class*='message-content']",
        "[class*='assistant'] [class*='content']",
        "[class*='answer']",
        "[class*='response']",
        "[class*='reply']",
        "[role='article']",
    ]

    LOADING_SELECTORS = [
        "button[aria-label*='Stop' i]",
        "button[aria-label*='stop' i]",
        "[class*='streaming']",
        "[class*='loading']",
        "[class*='generating']",
        "[class*='typing']",
    ]

    NEW_CHAT_SELECTORS = [
        "a[href='/']",
        "button[aria-label*='New' i]",
        "button[aria-label*='new' i]",
        "[class*='new-chat']",
        "[class*='newChat']",
    ]

    LOGIN_INDICATORS = [
        "input[type='email']",
        "input[type='password']",
        "input[type='phone']",
        "button[class*='login']",
        "[class*='sign-in']",
        "[class*='login']",
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

        log(f"[{self.name}] Chat pronto")
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
