"""
Driver para GLM (chat.z.ai).
Seletores confirmados via HTML do site (01/04/2026).
Modelo: GLM-4.7, DeepThink DESLIGADO.
"""

import time
from .base_driver import BaseDriver, set_clipboard, log


class GLMDriver(BaseDriver):
    name = "glm"
    url = "https://chat.z.ai"

    # Herda TIMEOUT_SEC = 1200 (20 min) do BaseDriver

    # --- SELETORES CONFIRMADOS ---

    INPUT_SELECTORS = [
        "textarea#chat-input",
        "textarea",
    ]

    SEND_SELECTORS = [
        "button#send-message-button",
        "button[type='submit']",
    ]

    RESPONSE_SELECTORS = [
        "div[class*='markdown']",
        "[class*='message-content']",
        "[class*='assistant'] [class*='content']",
        "[class*='answer']",
        "[class*='response']",
    ]

    LOADING_SELECTORS = [
        "button[aria-label*='Stop' i]",
        "[class*='streaming']",
        "[class*='loading']",
        "[class*='generating']",
    ]

    NEW_CHAT_SELECTORS = [
        "a[href='/']",
        "button[aria-label*='New' i]",
        "[class*='new-chat']",
    ]

    LOGIN_INDICATORS = [
        "input[type='email']",
        "input[type='password']",
        "input[type='phone']",
        "button[class*='login']",
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
                    break
            except Exception:
                continue

        # 1. Desligar DeepThink
        self._desligar_deepthink(page)

        # 2. Ligar Search (globo)
        self._ligar_search(page)

        log(f"[{self.name}] Chat pronto (Search ON, DeepThink OFF)")
        return True

    def _ligar_search(self, page):
        """Liga o botao de Search (globo) se estiver desligado."""
        try:
            # O botao de search e o que tem o icone de globo (viewBox 0 0 15 15)
            # Fica dentro de um <button> com aria-describedby, antes do DeepThink
            # Quando ativo, fica com bg azul/highlight; quando inativo, transparente
            result = page.evaluate("""() => {
                // Procurar o botao tooltip-trigger que contem o SVG do globo
                const triggers = document.querySelectorAll('button[data-tooltip-trigger]');
                for (const trigger of triggers) {
                    const svg = trigger.querySelector('svg[viewBox="0 0 15 15"]');
                    if (svg) {
                        // Encontrou o botao do globo - verificar o botao real dentro dele
                        const innerBtn = trigger.querySelector('button');
                        if (innerBtn) {
                            // Checar se esta ativo (tem classes de destaque)
                            const cls = innerBtn.className || '';
                            // Quando INATIVO: bg-transparent, text-gray
                            // Quando ATIVO: tem bg colorido
                            if (cls.includes('bg-transparent') || !cls.includes('bg-')) {
                                innerBtn.click();
                                return 'ligado';
                            }
                            return 'ja_ligado';
                        }
                        // Clicar no proprio trigger
                        trigger.click();
                        return 'ligado_trigger';
                    }
                }
                // Fallback: procurar qualquer botao com SVG viewBox 15x15 (globo)
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    const svg = btn.querySelector('svg[viewBox="0 0 15 15"]');
                    if (svg) {
                        btn.click();
                        return 'ligado_fallback';
                    }
                }
                return 'nao_encontrado';
            }""")

            if result and 'ligado' in result:
                time.sleep(0.5)
                log(f"[{self.name}] Search LIGADO ({result})")
            elif result == 'ja_ligado':
                log(f"[{self.name}] Search ja estava ligado")
            else:
                log(f"[{self.name}] [AVISO] Botao Search: {result}")
        except Exception as e:
            log(f"[{self.name}] [AVISO] Erro Search: {e}")

    def _desligar_deepthink(self, page):
        """Desliga DeepThink via atributo data-autothink do botao."""
        try:
            result = page.evaluate("""() => {
                // Seletor exato: botao com data-autothink
                const btn = document.querySelector('button[data-autothink]');
                if (!btn) return 'botao_nao_encontrado';

                const state = btn.getAttribute('data-autothink');
                if (state === 'true') {
                    btn.click();
                    return 'desligado';
                }
                return 'ja_desligado';
            }""")

            if result == 'desligado':
                time.sleep(0.5)
                log(f"[{self.name}] DeepThink DESLIGADO")
            elif result == 'ja_desligado':
                log(f"[{self.name}] DeepThink ja estava desligado")
            else:
                log(f"[{self.name}] [AVISO] DeepThink: {result}")
        except Exception as e:
            log(f"[{self.name}] [AVISO] Erro DeepThink: {e}")

    def colar_mensagem(self, page, texto):
        """GLM: colar no textarea#chat-input."""
        input_el = page.locator("textarea#chat-input")
        if input_el.count() == 0:
            # Fallback
            input_el = page.locator("textarea")
        if input_el.count() == 0:
            raise Exception(f"[{self.name}] Campo de input nao encontrado")

        input_el.first.click()
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
        """GLM: clicar no botao #send-message-button."""
        time.sleep(0.5)

        # Botao de envio exato
        btn = page.locator("button#send-message-button")
        if btn.count() > 0:
            try:
                btn.first.click()
                log(f"[{self.name}] Enviado via botao")
                return True
            except Exception:
                pass

        # Fallback
        for sel in self.SEND_SELECTORS:
            try:
                b = page.locator(sel)
                if b.count() > 0 and b.first.is_visible(timeout=2000):
                    b.first.click()
                    log(f"[{self.name}] Enviado via fallback")
                    return True
            except Exception:
                continue

        page.keyboard.press("Enter")
        log(f"[{self.name}] Enviado via Enter")
        return True
