"""
Setup Wine Classifier — Mistral (Chrome separado).
Abre Chrome para logar no Mistral.
Sessao salva em browser_state_mistral/.

Uso:
  python wine_classifier/setup_mistral.py
"""

import sys
import os
import time
import ctypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BROWSER_STATE = os.path.join(SCRIPT_DIR, "browser_state_mistral")


def popup(titulo, mensagem):
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass
    ctypes.windll.user32.MessageBoxW(0, str(mensagem), str(titulo), 0x40 | 0x1000)


def main():
    print("=== SETUP Wine Classifier — Mistral (Chrome separado) ===")
    print(f"Browser state: {BROWSER_STATE}")

    if os.path.exists(BROWSER_STATE) and os.listdir(BROWSER_STATE):
        print("[INFO] Ja existe estado salvo em browser_state_mistral/")
        resp = input("Continuar mesmo assim? (s/n): ").strip().lower()
        if resp != "s":
            print("Setup cancelado")
            return

    from playwright.sync_api import sync_playwright

    print("Abrindo Chrome (perfil Mistral)...")
    print("")
    print("INSTRUCOES:")
    print("  1. Faca login no Mistral: https://chat.mistral.ai/chat")
    print("  2. Depois de logar, FECHE O BROWSER (X)")
    print("  3. O estado sera salvo automaticamente")
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

        page = context.pages[0] if context.pages else context.new_page()
        print("Abrindo Mistral...")
        try:
            page.goto("https://chat.mistral.ai/chat", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            print("[AVISO] Mistral demorou, mas a aba foi aberta")

        popup(
            "Wine Classifier - Setup Mistral",
            "Faca login no Mistral Le Chat.\n\n"
            "Depois de logar, FECHE O BROWSER.",
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
    print("[OK] Setup Mistral concluido!")
    print(f"[OK] Estado salvo em: {BROWSER_STATE}")


if __name__ == "__main__":
    main()
