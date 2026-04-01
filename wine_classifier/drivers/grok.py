"""
Driver para Grok (grok.com) — modo Expert.
Copiado do Discovery. SPLIT_PROMPT desabilitado (prompt de vinho cabe inteiro).
"""

import time
from .base_driver import BaseDriver, log


class GrokDriver(BaseDriver):
    name = "grok"
    url = "https://grok.com"

    # Grok Expert pode demorar (thinking)
    TIMEOUT_SEC = 420
    STABLE_SEC = 30
    MIN_WAIT_SEC = 180

    INPUT_SELECTORS = [
        "textarea",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
        "div[contenteditable='plaintext-only']",
        "[contenteditable='true'][aria-label*='message' i]",
        "[contenteditable='true'][aria-label*='Ask' i]",
        "[class*='chat-input']",
        "[class*='input-area'] textarea",
    ]

    SEND_SELECTORS = [
        "button[aria-label*='Send' i]",
        "button[aria-label*='send' i]",
        "button[aria-label*='Submit' i]",
        "button[type='submit']",
        "button[class*='send']",
        "form button:last-of-type",
    ]

    RESPONSE_SELECTORS = [
        "[data-testid='message-content']",
        "div[class*='markdown']",
        "div[class*='message-text']",
        "div[class*='response']",
        "div[class*='assistant']",
        "[role='article']",
        ".message-bubble .markdown",
        ".response-message",
    ]

    LOADING_SELECTORS = [
        "button[aria-label*='Stop' i]",
        "button[aria-label*='stop' i]",
        "[data-testid='stop-button']",
        "[class*='streaming']",
        "[class*='loading']",
        "[class*='generating']",
    ]

    NEW_CHAT_SELECTORS = [
        "button[aria-label*='New' i]",
        "button[aria-label*='new' i]",
        "[data-testid='new-chat']",
        "[class*='new-chat']",
        "a[href='/']",
    ]

    LOGIN_INDICATORS = [
        "input[name='text']",
        "a[href*='login']",
        "[data-testid='loginButton']",
        "[class*='sign-in']",
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

        self._selecionar_expert(page)

        log(f"[{self.name}] Chat pronto (Expert)")
        return True

    def _selecionar_expert(self, page):
        """Seleciona modo Expert (Grok 3)."""
        try:
            current = page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const btn of btns) {
                        const text = btn.textContent.trim();
                        if (text === 'Expert') return 'expert';
                        if (text === 'Auto' || text === 'Mini') return text.toLowerCase();
                    }
                    return null;
                }
            """)

            if current == 'expert':
                log(f"[{self.name}] Modo Expert ja ativo")
                return True

            if not current:
                log(f"[{self.name}] [AVISO] Botao de modelo nao encontrado")
                return False

            # Clicar no botao de modelo pra abrir dropdown
            page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const btn of btns) {
                        const text = btn.textContent.trim();
                        if (text === 'Auto' || text === 'Mini') {
                            btn.click();
                            return;
                        }
                    }
                }
            """)
            time.sleep(2)

            # Clicar em Expert
            expert_clicked = page.evaluate("""
                () => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        const text = el.textContent.trim();
                        if (text === 'Expert') {
                            el.click();
                            return 'clicked';
                        }
                    }
                    for (const el of all) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        const text = el.textContent.trim();
                        if (text.includes('Expert') && text.length < 30 && el.tagName !== 'BODY') {
                            el.click();
                            return 'clicked_partial: ' + text;
                        }
                    }
                    return false;
                }
            """)

            if expert_clicked:
                time.sleep(1)
                log(f"[{self.name}] Modo Expert selecionado")
                return True
            else:
                page.keyboard.press("Escape")
                log(f"[{self.name}] [AVISO] Opcao Expert nao encontrada")

        except Exception as e:
            log(f"[{self.name}] [AVISO] Erro ao selecionar Expert: {e}")
        return False

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
