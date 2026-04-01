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
        """Seleciona modo Expert (Grok 3). Procura variações de nome."""
        try:
            # Passo 1: detectar modo atual
            current = page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const btn of btns) {
                        const text = btn.textContent.trim().toLowerCase();
                        if (text === 'expert' || text.includes('grok 3') || text.includes('grok3')) return 'expert';
                        if (text === 'auto' || text === 'mini' || text.includes('grok 2') ||
                            text === 'think' || text === 'default') return text;
                    }
                    // Tentar por aria-label ou data attributes
                    const modelBtns = document.querySelectorAll('[data-testid*="model"], [aria-label*="model" i], [aria-label*="Model" i]');
                    for (const btn of modelBtns) {
                        const text = btn.textContent.trim().toLowerCase();
                        if (text.includes('expert') || text.includes('grok 3')) return 'expert';
                        return 'modelo: ' + text;
                    }
                    return null;
                }
            """)

            log(f"[{self.name}] Modo detectado: {current}")

            if current == 'expert':
                log(f"[{self.name}] Modo Expert ja ativo")
                return True

            # Passo 2: clicar no seletor de modelo pra abrir dropdown
            page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const btn of btns) {
                        const text = btn.textContent.trim().toLowerCase();
                        if (text === 'auto' || text === 'mini' || text === 'think' ||
                            text === 'default' || text.includes('grok')) {
                            btn.click();
                            return true;
                        }
                    }
                    // Fallback: botao de modelo por atributos
                    const modelBtns = document.querySelectorAll('[data-testid*="model"], [aria-label*="model" i]');
                    for (const btn of modelBtns) {
                        btn.click();
                        return true;
                    }
                    return false;
                }
            """)
            time.sleep(2)

            # Passo 3: clicar em Expert no dropdown
            expert_clicked = page.evaluate("""
                () => {
                    // Match exato primeiro
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        const text = el.textContent.trim();
                        const textLower = text.toLowerCase();
                        if (text === 'Expert' || textLower === 'expert' ||
                            textLower.includes('grok 3') || textLower.includes('grok3')) {
                            if (text.length < 30 && el.tagName !== 'BODY' && el.tagName !== 'HTML') {
                                el.click();
                                return 'clicked: ' + text;
                            }
                        }
                    }
                    // Fallback: items de menu/opcoes
                    const items = document.querySelectorAll('[role="option"], [role="menuitem"], [role="menuitemradio"], li');
                    for (const item of items) {
                        const text = item.textContent.trim().toLowerCase();
                        if (text.includes('expert') || text.includes('grok 3')) {
                            item.click();
                            return 'clicked_item: ' + text;
                        }
                    }
                    return false;
                }
            """)

            if expert_clicked:
                time.sleep(1)
                log(f"[{self.name}] Modo Expert selecionado ({expert_clicked})")
                return True
            else:
                page.keyboard.press("Escape")
                log(f"[{self.name}] [AVISO] Opcao Expert nao encontrada no dropdown")

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
