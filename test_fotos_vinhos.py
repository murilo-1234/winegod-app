"""
Teste automatizado: enviar fotos de vinhos para API do WineGod e coletar respostas.
Objetivo: verificar identificacao e notas atribuidas pelo sistema.
"""
import base64
import json
import requests
import time
import os
import sys

API_URL = "https://winegod-app.onrender.com/api/chat"
FOTOS_DIR = r"C:\winegod\fotos-vinhos-testes"
SESSION_PREFIX = "test-audit-fotos"

# Fotos selecionadas com descricao do que EU vejo na foto (ground truth)
FOTOS_TESTE = [
    {
        "file": "2.jpeg",
        "desc": "Rotulo close-up: Pena Vermelha Reserva, vinho portugues, R$89.99",
        "msg": "Que vinho é esse? Me dá a nota dele e se vale a pena pelo preço.",
        "vinhos_esperados": ["Pena Vermelha Reserva"],
    },
    {
        "file": "10.jpeg",
        "desc": "Dois rotulos: Finca Las Moras Cabernet Sauvignon 2024 (Argentina) + Trivento Malbec de Fuego Reserve (Mendoza)",
        "msg": "Quais são esses dois vinhos? Me dá o ranking dos dois com nota.",
        "vinhos_esperados": ["Finca Las Moras Cabernet Sauvignon", "Trivento Malbec de Fuego"],
    },
    {
        "file": "3.jpeg",
        "desc": "Contada 1926 Chianti (branco) + Contada 1926 Primitivo (azul escuro), R$59",
        "msg": "Me fala desses vinhos. Qual é melhor? Dá nota pra cada um.",
        "vinhos_esperados": ["Contada 1926 Chianti", "Contada 1926 Primitivo"],
    },
    {
        "file": "5.jpeg",
        "desc": "D'Eugenio Crianza La Mancha (espanhol), R$54, prateleira com varias garrafas",
        "msg": "Que vinho é esse? Vale a pena? Qual a nota?",
        "vinhos_esperados": ["D'Eugenio Crianza"],
    },
    {
        "file": "9.jpeg",
        "desc": "She Noir Pinot Noir (R$189.99) ao lado de Freixenet 0.0 (sem alcool, R$129)",
        "msg": "Quais são esses vinhos? Me dá nota e opinião de cada um.",
        "vinhos_esperados": ["She Noir Pinot Noir", "Freixenet 0.0"],
    },
    {
        "file": "15.jpeg",
        "desc": "Perez Cruz Limited Edition Cabernet Franc (Chile, R$144.99) + Doña Dominga Reserva (R$63.99)",
        "msg": "Me fala desses dois vinhos. Ranking com nota, por favor.",
        "vinhos_esperados": ["Perez Cruz Limited Edition", "Doña Dominga Reserva"],
    },
    {
        "file": "16.jpeg",
        "desc": "Perez Cruz Piedra Seca (R$159.99) + Perez Cruz Grenache (R$183.99)",
        "msg": "Quais são esses vinhos chilenos? Qual vale mais a pena? Nota de cada um.",
        "vinhos_esperados": ["Perez Cruz Piedra Seca", "Perez Cruz Grenache"],
    },
    {
        "file": "1.jpeg",
        "desc": "Prateleira grande de supermercado com muitos vinhos variados",
        "msg": "Que vinhos você consegue ver nessa prateleira? Me dá um ranking dos melhores.",
        "vinhos_esperados": ["SHELF - multiplos vinhos"],
    },
    {
        "file": "13.jpeg",
        "desc": "Doña Dominga vinhos (dois tipos) na prateleira, com etiquetas de preço",
        "msg": "Quais vinhos são esses? Me dá nota e opinião.",
        "vinhos_esperados": ["Doña Dominga"],
    },
    {
        "file": "21.jpeg",
        "desc": "Prateleira premium: Dom Perignon, Krug, espumantes caros",
        "msg": "Que espumantes são esses? Me dá o ranking com notas.",
        "vinhos_esperados": ["Dom Perignon", "Krug"],
    },
    {
        "file": "24.jpeg",
        "desc": "Freixenet + Corvezzo Prosecco na prateleira",
        "msg": "Quais são esses espumantes? Nota e opinião de cada.",
        "vinhos_esperados": ["Freixenet", "Corvezzo"],
    },
    {
        "file": "14.jpeg",
        "desc": "Amaral vinhos (chileno) em oferta + outros vinhos embaixo",
        "msg": "Quais vinhos tem nessa foto? Me dá ranking dos que conseguir identificar.",
        "vinhos_esperados": ["Amaral"],
    },
]

def encode_image(filepath):
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def send_photo(foto_info, index):
    filepath = os.path.join(FOTOS_DIR, foto_info["file"])
    if not os.path.exists(filepath):
        return {"error": f"File not found: {filepath}"}

    img_b64 = encode_image(filepath)
    session_id = f"{SESSION_PREFIX}-{index:03d}"

    payload = {
        "message": foto_info["msg"],
        "image": img_b64,
        "session_id": session_id,
    }

    print(f"\n{'='*80}")
    print(f"TESTE {index+1}/{len(FOTOS_TESTE)}: {foto_info['file']}")
    print(f"Ground truth: {foto_info['desc']}")
    print(f"Mensagem: {foto_info['msg']}")
    print(f"Vinhos esperados: {foto_info['vinhos_esperados']}")
    print(f"Enviando...")

    start = time.time()
    try:
        resp = requests.post(API_URL, json=payload, timeout=120)
        elapsed = time.time() - start

        if resp.status_code == 200:
            data = resp.json()
            response_text = data.get("response", "")
            print(f"Status: 200 OK ({elapsed:.1f}s)")
            print(f"Modelo: {data.get('model', 'unknown')}")
            print(f"\nRESPOSTA DO BACO:")
            print("-" * 40)
            print(response_text[:2000])
            if len(response_text) > 2000:
                print(f"\n... (truncado, total: {len(response_text)} chars)")
            print("-" * 40)
            return {
                "status": 200,
                "response": response_text,
                "model": data.get("model"),
                "time": elapsed,
            }
        else:
            print(f"Status: {resp.status_code} ({elapsed:.1f}s)")
            print(f"Body: {resp.text[:500]}")
            return {"status": resp.status_code, "error": resp.text[:500], "time": elapsed}
    except Exception as e:
        elapsed = time.time() - start
        print(f"ERRO: {e} ({elapsed:.1f}s)")
        return {"error": str(e), "time": elapsed}

def main():
    results = []

    print("=" * 80)
    print("TESTE DE FOTOS DE VINHOS — WineGod API")
    print(f"API: {API_URL}")
    print(f"Total de fotos: {len(FOTOS_TESTE)}")
    print("=" * 80)

    for i, foto in enumerate(FOTOS_TESTE):
        result = send_photo(foto, i)
        result["file"] = foto["file"]
        result["ground_truth"] = foto["desc"]
        result["vinhos_esperados"] = foto["vinhos_esperados"]
        results.append(result)

        # Intervalo entre requests para nao sobrecarregar
        if i < len(FOTOS_TESTE) - 1:
            print(f"\nAguardando 3s antes do proximo teste...")
            time.sleep(3)

    # Salvar resultados completos
    output_path = os.path.join(os.path.dirname(__file__), "test_fotos_resultados.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n\nResultados salvos em: {output_path}")

    # Resumo
    print(f"\n{'='*80}")
    print("RESUMO")
    print(f"{'='*80}")
    ok = sum(1 for r in results if r.get("status") == 200)
    err = len(results) - ok
    print(f"Sucesso: {ok}/{len(results)}")
    print(f"Erros: {err}/{len(results)}")
    avg_time = sum(r.get("time", 0) for r in results) / len(results)
    print(f"Tempo medio: {avg_time:.1f}s")

if __name__ == "__main__":
    main()
