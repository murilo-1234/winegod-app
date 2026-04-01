"""
BaseDriver para Wine Classifier.
Versao enxuta do Discovery base_driver — so paste/send/poll.
Clipboard do Windows embutido (ctypes 64-bit safe).
"""

import time
import ctypes


# === Clipboard Windows (copiado de agent_discovery/utils.py) ===

def set_clipboard(text):
    """Copia texto para o clipboard do Windows (64-bit safe)."""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

    if not user32.OpenClipboard(0):
        raise Exception("Nao conseguiu abrir clipboard")

    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16le") + b"\x00\x00"
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            raise Exception("GlobalAlloc falhou")
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            kernel32.GlobalFree(h)
            raise Exception("GlobalLock falhou")
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            raise Exception("SetClipboardData falhou")
    finally:
        user32.CloseClipboard()


# === Log simples ===

def log(msg):
    from datetime import datetime
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


class BaseDriver:
    name = "base"
    url = ""

    # --- Seletores CSS (subclasses DEVEM sobrescrever) ---
    INPUT_SELECTORS = []
    SEND_SELECTORS = []
    RESPONSE_SELECTORS = []
    LOADING_SELECTORS = []
    NEW_CHAT_SELECTORS = []
    LOGIN_INDICATORS = []

    # --- Timeouts ---
    TIMEOUT_SEC = 420       # 7 min max
    STABLE_SEC = 30         # texto estavel = completo
    MIN_WAIT_SEC = 180      # esperar minimo antes de checar estabilidade
    CHECK_SEC = 3

    # Prompt grande: esperar mais apos colar
    WAIT_AFTER_PASTE_SEC = 1.0

    def abrir_novo_chat(self, page):
        """Navega para URL e inicia novo chat."""
        log(f"[{self.name}] Abrindo {self.url}")
        page.goto(self.url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)

        for sel in self.NEW_CHAT_SELECTORS:
            try:
                btn = page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible(timeout=3000):
                    btn.first.click()
                    time.sleep(2)
                    log(f"[{self.name}] Novo chat iniciado via botao")
                    return True
            except Exception:
                continue

        log(f"[{self.name}] Usando pagina atual como novo chat")
        return True

    def _find_input(self, page):
        """Encontra o campo de input."""
        for sel in self.INPUT_SELECTORS:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible(timeout=3000):
                    return loc.first
            except Exception:
                continue
        return None

    def colar_mensagem(self, page, texto):
        """Cola texto no campo de input via clipboard do Windows."""
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

        wait = self.WAIT_AFTER_PASTE_SEC
        if len(texto) > 10000:
            wait = 4.0
        elif len(texto) > 5000:
            wait = 2.5
        time.sleep(wait)

        log(f"[{self.name}] Texto colado ({len(texto)} chars)")

    def enviar_mensagem(self, page):
        """Envia a mensagem (tenta botao, depois Enter)."""
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

    def _get_response_text(self, page):
        """Pega o texto da ultima resposta da IA."""
        for sel in self.RESPONSE_SELECTORS:
            try:
                elements = page.locator(sel)
                count = elements.count()
                if count > 0:
                    text = elements.nth(count - 1).inner_text(timeout=2000)
                    if text and len(text.strip()) > 1:
                        return text.strip()
            except Exception:
                continue
        return ""

    def _is_loading(self, page):
        """Verifica se a IA ainda esta gerando resposta."""
        for sel in self.LOADING_SELECTORS:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible(timeout=1000):
                    return True
            except Exception:
                continue
        return False

    def detectar_bloqueio(self, page):
        """Detecta sessao expirada ou CAPTCHA."""
        for sel in self.LOGIN_INDICATORS:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible(timeout=1000):
                    return "sessao_expirada"
            except Exception:
                continue

        try:
            url = page.url.lower()
            if "challenge" in url or "captcha" in url or "verify" in url:
                return "captcha"
        except Exception:
            pass

        return None
