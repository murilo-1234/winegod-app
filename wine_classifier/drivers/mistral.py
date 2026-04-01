"""
Driver para Mistral AI Le Chat (chat.mistral.ai).
Copiado do Discovery, modo Rapido (padrao).
"""

import time
from .base_driver import BaseDriver, set_clipboard, log


class MistralDriver(BaseDriver):
    name = "mistral"
    url = "https://chat.mistral.ai/chat"

    TIMEOUT_SEC = 150      # 2.5 min max (cada aba termina em 1-1.5 min)
    STABLE_SEC = 10        # texto estavel 10s = completo
    MIN_WAIT_SEC = 45      # 45s minimo

    INPUT_SELECTORS = [
        "div.ProseMirror[contenteditable='true']",
        "div[contenteditable='true']",
    ]

    SEND_SELECTORS = [
        "button[type='submit']",
    ]

    RESPONSE_SELECTORS = [
        "div[class*='markdown-container']",
        "div[class*='group/message']",
    ]

    LOADING_SELECTORS = [
        "button[aria-label*='Stop' i]",
        "button[aria-label*='Parar' i]",
        "[class*='animate-spin']",
    ]

    NEW_CHAT_SELECTORS = [
        "a[href='/chat']",
    ]

    LOGIN_INDICATORS = [
        "input[type='email']",
        "input[type='password']",
        "button[class*='login']",
        "button[class*='sign']",
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

        self._selecionar_rapido(page)

        log(f"[{self.name}] Chat pronto (Rapido)")
        return True

    def _selecionar_rapido(self, page):
        """Garante que Mistral esta no modo Rapido (nao Pesquisa nem Refletir)."""
        try:
            mode = page.evaluate("""() => {
                const btns = document.querySelectorAll('button[type="button"]');
                for (const btn of btns) {
                    const text = btn.innerText.trim();
                    if (['Rápido', 'Rapido', 'Fast', 'Pesquisa', 'Search', 'Refletir', 'Reflect'].includes(text)) {
                        return text;
                    }
                }
                return null;
            }""")

            if mode and mode in ('Rápido', 'Rapido', 'Fast'):
                log(f"[{self.name}] Modo Rapido ja ativo")
                return True

            if mode:
                # Esta em outro modo (Pesquisa/Refletir) — clicar pra trocar
                log(f"[{self.name}] Modo atual: {mode} — trocando pra Rapido")
                page.evaluate("""() => {
                    const btns = document.querySelectorAll('button[type="button"]');
                    for (const btn of btns) {
                        const text = btn.innerText.trim();
                        if (['Rápido', 'Rapido', 'Fast'].includes(text)) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                time.sleep(1)
                log(f"[{self.name}] Modo Rapido selecionado")
                return True

            log(f"[{self.name}] Modo nao identificado — usando padrao")
        except Exception as e:
            log(f"[{self.name}] [AVISO] Erro ao verificar modo: {e}")
        return False

    def colar_mensagem(self, page, texto):
        """Mistral: colar via JS focus + clipboard."""
        focused = page.evaluate("""() => {
            const selectors = [
                'div.ProseMirror[contenteditable="true"]',
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
        """Mistral: enviar via JS (botao submit hidden)."""
        time.sleep(0.5)

        sent = page.evaluate("""() => {
            const btns = document.querySelectorAll('button[type="submit"]');
            for (const btn of btns) {
                const text = btn.innerText.trim();
                if (!text || text.length < 3) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")

        if sent:
            log(f"[{self.name}] Enviado via botao")
            return True

        page.keyboard.press("Enter")
        log(f"[{self.name}] Enviado via Enter")
        return True

    def _get_response_text(self, page):
        try:
            md = page.locator("div[class*='markdown-container']")
            count = md.count()
            if count > 0:
                text = md.nth(count - 1).inner_text(timeout=3000)
                if text and len(text.strip()) > 1:
                    return text.strip()
        except Exception:
            pass

        try:
            msgs = page.locator("div[class*='group/message']")
            count = msgs.count()
            if count > 0:
                text = msgs.nth(count - 1).inner_text(timeout=3000)
                if text and len(text.strip()) > 1:
                    return text.strip()
        except Exception:
            pass

        return ""
