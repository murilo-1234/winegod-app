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
                    break
            except Exception:
                continue

        # 1. Selecionar modelo GLM-4.7
        self._selecionar_glm47(page)

        # 2. Garantir DeepThink DESLIGADO
        self._evitar_deepthink(page)

        log(f"[{self.name}] Chat pronto (GLM-4.7, sem DeepThink)")
        return True

    def _selecionar_glm47(self, page):
        """Seleciona modelo GLM-4.7 no seletor de modelo."""
        try:
            result = page.evaluate("""() => {
                // Procurar botao/seletor de modelo
                const all = document.querySelectorAll('button, [role="combobox"], [class*="model"], [class*="select"]');
                for (const el of all) {
                    const text = (el.textContent || '').trim().toLowerCase();
                    // Ja esta em GLM-4.7?
                    if (text.includes('glm-4.7') || text.includes('glm4.7')) {
                        return 'ja_selecionado';
                    }
                    // Encontrou seletor de modelo (mostra outro modelo)
                    if (text.includes('glm') && el.tagName === 'BUTTON') {
                        el.click();
                        return 'dropdown_aberto: ' + text;
                    }
                }
                // Tentar por aria-label
                const btns = document.querySelectorAll('button[aria-label*="model" i], button[aria-label*="modelo" i]');
                for (const btn of btns) {
                    btn.click();
                    return 'dropdown_aberto_aria';
                }
                // Tentar qualquer dropdown/select visivel na area do input
                const selects = document.querySelectorAll('[class*="dropdown"], [class*="selector"], [class*="picker"]');
                for (const sel of selects) {
                    const rect = sel.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        sel.click();
                        return 'dropdown_generico';
                    }
                }
                return 'nao_encontrado';
            }""")

            if result == 'ja_selecionado':
                log(f"[{self.name}] GLM-4.7 ja selecionado")
                return True

            if result and result.startswith('dropdown'):
                log(f"[{self.name}] Seletor aberto ({result}), procurando GLM-4.7...")
                time.sleep(1)

                # Clicar em GLM-4.7 no dropdown
                selected = page.evaluate("""() => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        const text = (el.textContent || '').trim().toLowerCase();
                        if ((text.includes('glm-4.7') || text.includes('glm4.7') || text === '4.7') &&
                            text.length < 30) {
                            el.click();
                            return 'selecionado: ' + text;
                        }
                    }
                    // Fallback: procurar por "4.7" em qualquer item de lista
                    const items = document.querySelectorAll('[role="option"], [role="menuitem"], li');
                    for (const item of items) {
                        const text = (item.textContent || '').trim();
                        if (text.includes('4.7')) {
                            item.click();
                            return 'selecionado_lista: ' + text;
                        }
                    }
                    return false;
                }""")

                if selected:
                    time.sleep(1)
                    log(f"[{self.name}] GLM-4.7 selecionado ({selected})")
                    return True
                else:
                    page.keyboard.press("Escape")
                    log(f"[{self.name}] [AVISO] GLM-4.7 nao encontrado no dropdown")
            else:
                log(f"[{self.name}] [AVISO] Seletor de modelo nao encontrado")

        except Exception as e:
            log(f"[{self.name}] [AVISO] Erro ao selecionar GLM-4.7: {e}")
        return False

    def _evitar_deepthink(self, page):
        """Desativa DeepThink (toggle on/off). Sempre clicar se estiver ligado."""
        try:
            # Estrategia 1: procurar qualquer elemento com texto deepthink e clicar se ativo
            result = page.evaluate("""() => {
                // Procurar TUDO que tenha deepthink no texto, classe, aria, etc.
                const all = document.querySelectorAll('*');
                const candidates = [];

                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;

                    const text = (el.textContent || '').trim().toLowerCase();
                    const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                    const className = (el.className || '').toString().toLowerCase();
                    const id = (el.id || '').toLowerCase();

                    const isDeepThink = text.includes('deepthink') || text.includes('deep think') ||
                                       ariaLabel.includes('deepthink') || ariaLabel.includes('deep think') ||
                                       className.includes('deepthink') || className.includes('deep-think') ||
                                       id.includes('deepthink') || id.includes('deep-think');

                    if (!isDeepThink) continue;
                    if (el.tagName === 'BODY' || el.tagName === 'HTML') continue;
                    if (text.length > 100) continue;

                    candidates.push({
                        tag: el.tagName,
                        text: text.substring(0, 50),
                        class: className.substring(0, 60),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height),
                    });

                    // Checar se e um toggle/switch/checkbox
                    const isToggle = el.getAttribute('role') === 'switch' ||
                                    el.getAttribute('role') === 'checkbox' ||
                                    el.tagName === 'INPUT' && el.type === 'checkbox' ||
                                    className.includes('toggle') || className.includes('switch');

                    const isActive = el.classList.contains('active') ||
                                    el.getAttribute('aria-checked') === 'true' ||
                                    el.getAttribute('data-state') === 'checked' ||
                                    el.getAttribute('data-state') === 'on' ||
                                    el.classList.contains('on') ||
                                    el.classList.contains('checked') ||
                                    el.checked === true ||
                                    className.includes('active') ||
                                    className.includes('checked') ||
                                    className.includes('selected');

                    if (isToggle) {
                        if (isActive) {
                            el.click();
                            return 'desativado_toggle: ' + el.tagName + ' ' + text.substring(0, 30);
                        }
                        return 'toggle_ja_off';
                    }
                }

                // Estrategia 2: procurar o switch mais proximo do texto "DeepThink"
                for (const el of all) {
                    const text = (el.textContent || '').trim().toLowerCase();
                    if (text === 'deepthink' || text === 'deep think') {
                        // Procurar switch/toggle proximo (irmao, pai, vizinho)
                        const parent = el.parentElement;
                        if (!parent) continue;

                        const siblings = parent.querySelectorAll('[role="switch"], [role="checkbox"], input[type="checkbox"], [class*="toggle"], [class*="switch"]');
                        for (const sib of siblings) {
                            const isActive = sib.getAttribute('aria-checked') === 'true' ||
                                            sib.getAttribute('data-state') === 'checked' ||
                                            sib.classList.contains('active') ||
                                            sib.classList.contains('on') ||
                                            sib.checked === true;
                            if (isActive) {
                                sib.click();
                                return 'desativado_sibling';
                            }
                            return 'sibling_ja_off';
                        }

                        // Se nao achou toggle, clicar no proprio parent (pode ser o toggle)
                        const parentClass = (parent.className || '').toString().toLowerCase();
                        if (parentClass.includes('toggle') || parentClass.includes('switch') ||
                            parent.getAttribute('role') === 'switch') {
                            const isActive = parent.classList.contains('active') ||
                                            parent.getAttribute('aria-checked') === 'true';
                            if (isActive) {
                                parent.click();
                                return 'desativado_parent';
                            }
                            return 'parent_ja_off';
                        }
                    }
                }

                if (candidates.length > 0) {
                    return 'encontrou_mas_nao_toggle: ' + JSON.stringify(candidates.slice(0, 3));
                }
                return 'nao_encontrado';
            }""")

            log(f"[{self.name}] DeepThink check: {result}")

            if result and 'desativado' in result:
                time.sleep(1)
                log(f"[{self.name}] DeepThink DESLIGADO com sucesso")
            elif result and ('ja_off' in result or 'toggle_ja_off' in result):
                log(f"[{self.name}] DeepThink ja estava desligado")
            elif result and 'nao_encontrado' in result:
                log(f"[{self.name}] Toggle DeepThink nao encontrado na pagina")
            else:
                log(f"[{self.name}] [AVISO] DeepThink status incerto: {result}")
        except Exception as e:
            log(f"[{self.name}] [AVISO] Erro ao verificar DeepThink: {e}")

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
