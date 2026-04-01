"""
Setup Wine Classifier — Chrome.
Abre Chrome para logar em Mistral, Gemini e Grok.
Sessao salva em browser_state_chrome/.

Uso:
  python wine_classifier/setup_chrome.py
"""

import sys
import os
import time
import ctypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BROWSER_STATE = os.path.join(SCRIPT_DIR, "browser_state_chrome")

IAS = [
    ("Mistral", "https://chat.mistral.ai/chat"),
    ("Gemini", "https://gemini.google.com/app"),
    ("Grok", "https://grok.com"),
]


def popup(titulo, mensagem):
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass
    ctypes.windll.user32.MessageBoxW(0, str(mensagem), str(titulo), 0x40 | 0x1000)


def main():
    print("=== SETUP Wine Classifier — Chrome ===")
    print(f"Browser state: {BROWSER_STATE}")

    if os.path.exists(BROWSER_STATE) and os.listdir(BROWSER_STATE):
        print("[INFO] Ja existe estado salvo em browser_state_chrome/")
        resp = input("Continuar mesmo assim? (s/n): ").strip().lower()
        if resp != "s":
            print("Setup cancelado")
            return

    from playwright.sync_api import sync_playwright

    print("Abrindo Chrome...")
    print("")
    print("INSTRUCOES:")
    print("  1. O Chrome vai abrir com 3 abas (uma por IA)")
    print("  2. Faca login em TODAS:")
    for name, url in IAS:
        print(f"     - {name}: {url}")
    print("  3. Depois de logar em todas, FECHE O BROWSER (X)")
    print("  4. O estado sera salvo automaticamente")
    print("")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_STATE,
            channel="chrome",
            headless=False,
            viewport={"width": 1366, "height": 768},
            locale="pt-BR",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        for i, (name, url) in enumerate(IAS):
            if i == 0 and context.pages:
                page = context.pages[0]
            else:
                page = context.new_page()
            print(f"Abrindo {name}...")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                print(f"[AVISO] {name} demorou, mas a aba foi aberta")

        popup(
            "Wine Classifier - Setup Chrome",
            "Faca login nas 3 IAs:\n\n"
            "1. Mistral\n"
            "2. Gemini\n"
            "3. Grok\n\n"
            "Depois de logar em todas, FECHE O BROWSER.",
        )

        print("Aguardando fechar o browser...")
        try:
            while True:
                try:
                    _ = context.pages
                    time.sleep(2)
                except Exception:
                    break
        except Exception:
            pass

        try:
            context.close()
        except Exception:
            pass

    print("")
    print("[OK] Setup Chrome concluido!")
    print(f"[OK] Estado salvo em: {BROWSER_STATE}")


if __name__ == "__main__":
    main()
