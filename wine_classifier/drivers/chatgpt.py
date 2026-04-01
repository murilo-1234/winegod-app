"""
Driver para ChatGPT (chatgpt.com).
Copiado do Discovery. Sem thinking mode. SPLIT_PROMPT desabilitado.
"""

import time
from .base_driver import BaseDriver, set_clipboard, log


class ChatGPTDriver(BaseDriver):
    name = "chatgpt"
    url = "https://chatgpt.com"

    TIMEOUT_SEC = 2700     # 45 min (ChatGPT demora ~35 min)
    STABLE_SEC = 30
    MIN_WAIT_SEC = 300     # 5 min

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

        # Garantir modelo padrao (nao pensamento estendido)
        self._selecionar_modelo_padrao(page)

        log(f"[{self.name}] Chat pronto (modo padrao)")
        return True

    def _selecionar_modelo_padrao(self, page):
        """Garante que ChatGPT esta no modelo padrao (GPT-4o), nao em o3/o4-mini/thinking."""
        try:
            # Verificar se tem seletor de modelo visivel
            model_selected = page.evaluate("""() => {
                // Procurar botao do seletor de modelo
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    const text = btn.textContent.trim().toLowerCase();
                    // Se ja esta em ChatGPT/4o/padrao, tudo ok
                    if (text.includes('chatgpt') || text.includes('4o')) {
                        return 'padrao';
                    }
                    // Se esta em modelo de pensamento
                    if (text.includes('o3') || text.includes('o4') || text.includes('o1') ||
                        text.includes('reason') || text.includes('think')) {
                        return 'thinking: ' + text;
                    }
                }
                return null;
            }""")

            if model_selected == 'padrao':
                log(f"[{self.name}] Modelo padrao ja ativo")
                return True

            if model_selected and model_selected.startswith('thinking'):
                log(f"[{self.name}] Modelo atual: {model_selected} — trocando pra padrao")

                # Clicar no seletor de modelo
                page.evaluate("""() => {
                    const btn = document.querySelector('button[aria-label*="Model" i], button[aria-label*="Modelo" i], button[aria-label*="odel"]');
                    if (btn) { btn.click(); return true; }
                    // Fallback: procurar botao com texto do modelo
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        const text = b.textContent.trim().toLowerCase();
                        if (text.includes('o3') || text.includes('o4') || text.includes('o1')) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                time.sleep(1)

                # Selecionar ChatGPT/4o no dropdown
                selected = page.evaluate("""() => {
                    const all = document.querySelectorAll('[role="option"], [role="menuitem"], div, span');
                    for (const el of all) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        const text = el.textContent.trim().toLowerCase();
                        if ((text.includes('chatgpt') || text.includes('4o')) &&
                            !text.includes('o4-mini') && text.length < 30) {
                            el.click();
                            return 'selected: ' + text;
                        }
                    }
                    return false;
                }""")

                if selected:
                    time.sleep(1)
                    log(f"[{self.name}] Modelo padrao selecionado ({selected})")
                    return True
                else:
                    page.keyboard.press("Escape")
                    log(f"[{self.name}] [AVISO] Nao encontrou opcao padrao no dropdown")

            else:
                log(f"[{self.name}] Seletor de modelo nao encontrado — usando padrao")

        except Exception as e:
            log(f"[{self.name}] [AVISO] Erro ao verificar modelo: {e}")
        return False

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
