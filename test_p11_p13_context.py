"""Teste temporario de contexto P11/P13. NAO e arquivo de producao. Pode deletar depois."""
import sys
sys.stdout.reconfigure(encoding='utf-8')


def build_image_context(ocr_result):
    """Versao CORRETA do builder de contexto (como deveria estar em chat.py)."""
    image_type = ocr_result.get('image_type', '')
    if image_type == 'label':
        search_text = ocr_result.get('search_text', '')
        ocr_data = ocr_result.get('ocr_result', {})
        price = ocr_data.get('price') if isinstance(ocr_data, dict) else None
        parts = [f'OCR identificou: {search_text}']
        if price:
            parts.append(f'Preco visivel na foto: {price}')
        return (
            f"[O usuario enviou foto de um rotulo. {'. '.join(parts)}. "
            f"Use search_wine para buscar este vinho e responda sobre ele.]"
        )
    elif image_type == 'screenshot':
        wines = ocr_result.get('wines', [])
        if wines:
            wine_parts = []
            for w in wines:
                wp = w.get('name', '?')
                if w.get('price'):
                    wp += f" (preco: {w['price']})"
                if w.get('rating'):
                    wp += f" (nota: {w['rating']})"
                wine_parts.append(wp)
            return (
                f"[O usuario enviou screenshot com {len(wines)} vinho(s): {'; '.join(wine_parts)}. "
                f"Use search_wine para buscar cada vinho e responda sobre eles.]"
            )
        return "[O usuario enviou screenshot mas nenhum vinho foi identificado.]"
    elif image_type == 'shelf':
        wines = ocr_result.get('wines', [])
        if wines:
            wine_parts = []
            for w in wines:
                wp = w.get('name', '?')
                if w.get('price'):
                    wp += f" (preco: {w['price']})"
                wine_parts.append(wp)
            return (
                f"[O usuario enviou foto de prateleira. "
                f"Vinhos identificados: {'; '.join(wine_parts)}. "
                f"Use search_wine para buscar os vinhos legiveis e responda sobre eles.]"
            )
        return "[O usuario enviou foto de prateleira mas nenhum rotulo foi legivel.]"
    return "[O usuario tentou enviar uma foto mas nao foi possivel identificar o vinho.]"


def build_batch_context(batch_result):
    """Versao CORRETA do builder de batch."""
    parts = []
    for label in batch_result.get('labels', []):
        search_text = label.get('search_text', '')
        ocr_data = label.get('ocr_result', {})
        price = ocr_data.get('price') if isinstance(ocr_data, dict) else None
        entry = f"Rotulo: {search_text}"
        if price:
            entry += f" (preco: {price})"
        parts.append(entry)
    for ss in batch_result.get('screenshots', []):
        wines = ss.get('wines', [])
        if wines:
            wine_parts = []
            for w in wines:
                wp = w.get('name', '?')
                if w.get('price'):
                    wp += f" (preco: {w['price']})"
                if w.get('rating'):
                    wp += f" (nota: {w['rating']})"
                wine_parts.append(wp)
            parts.append(f"Screenshot: {'; '.join(wine_parts)}")
    for shelf in batch_result.get('shelves', []):
        wines = shelf.get('wines', [])
        if wines:
            wine_parts = []
            for w in wines:
                wp = w.get('name', '?')
                if w.get('price'):
                    wp += f" (preco: {w['price']})"
                wine_parts.append(wp)
            parts.append(f"Prateleira: {'; '.join(wine_parts)}")
    errors = batch_result.get('errors', [])
    if errors:
        parts.append(f"{len(errors)} imagem(ns) sem vinho")
    if not parts:
        return "[O usuario enviou fotos mas nenhum vinho foi identificado.]"
    wines_text = " | ".join(parts)
    return (
        f"[O usuario enviou {batch_result.get('image_count', 0)} foto(s). {wines_text}. "
        f"Use search_wine para buscar estes vinhos e responda sobre eles.]"
    )


# ====== CASO 1: Label com preco (foto 2) ======
print("=" * 70)
print("CASO 1 - Label com preco (foto 2)")
print("=" * 70)
caso1 = {
    'image_type': 'label',
    'search_text': 'Pena Vermelha Reserva Santos & Seixo Wine 2021 Tejo',
    'ocr_result': {'name': 'Pena Vermelha Reserva', 'producer': 'Santos & Seixo Wine',
                   'vintage': '2021', 'region': 'Tejo', 'grape': None, 'price': 'R$ 89,99'}
}
ctx1 = build_image_context(caso1)
print(f"CONTEXTO:\n{ctx1}")
print(f"  Preco foto no contexto: {'SIM' if '89,99' in ctx1 else 'NAO'}")
print(f"  Garrafas/contagem: {'FALHA' if 'garrafas' in ctx1.lower() or '~' in ctx1 else 'OK'}")

# ====== CASO 2: Shelf foto 11 ======
print("\n" + "=" * 70)
print("CASO 2 - Shelf foto 11 (MontGras)")
print("=" * 70)
caso2 = {
    'image_type': 'shelf',
    'wines': [
        {'name': 'MontGras Aura Reserva Cabernet Sauvignon', 'price': 'R$ 69,99'},
        {'name': 'MontGras Aura Reserva Merlot', 'price': 'R$ 69,99'},
        {'name': 'MontGras Aura Reserva Carmenere', 'price': 'R$ 54,99'},
        {'name': 'MontGras Aura Reserva Pinot Noir', 'price': 'R$ 54,99'},
        {'name': 'Casa Silva Reserva', 'price': None},
    ],
    'total_visible': 6
}
ctx2 = build_image_context(caso2)
print(f"CONTEXTO:\n{ctx2}")
print(f"  total_visible no texto: {'FALHA' if '~6' in ctx2 or 'total_visible' in ctx2 or '6 garrafas' in ctx2 else 'OK'}")
print(f"  Garrafas: {'FALHA' if 'garrafas' in ctx2.lower() else 'OK'}")
print(f"  Precos da foto: {'SIM' if '69,99' in ctx2 and '54,99' in ctx2 else 'NAO'}")

# ====== CASO 3: Shelf foto 12 ======
print("\n" + "=" * 70)
print("CASO 3 - Shelf foto 12 (prateleira grande)")
print("=" * 70)
caso3 = {
    'image_type': 'shelf',
    'wines': [
        {'name': 'BALDUZZI Grand Reserva', 'price': 'R$ 169,99'},
        {'name': 'MONTGRAS', 'price': 'R$ 109,99'},
        {'name': 'AMARAL', 'price': 'R$ 99,99'},
        {'name': 'CASTILLO de MOLINA', 'price': 'R$ 89,99'},
        {'name': 'BALDUZZI Varietal', 'price': 'R$ 29,99'},
        {'name': 'MONTGRAS Aura', 'price': 'R$ 89,99'},
    ],
    'total_visible': 10
}
ctx3 = build_image_context(caso3)
print(f"CONTEXTO:\n{ctx3}")
print(f"  total_visible: {'FALHA' if '~10' in ctx3 or '10 garrafas' in ctx3 else 'OK'}")
print(f"  Precos: {'SIM' if '169,99' in ctx3 else 'NAO'}")

# ====== CASO 4: Shelf foto 15 ======
print("\n" + "=" * 70)
print("CASO 4 - Shelf foto 15 (Perez Cruz + Dominga)")
print("=" * 70)
caso4 = {
    'image_type': 'shelf',
    'wines': [
        {'name': 'Perez Cruz Limited Edition Cabernet Franc', 'price': 'R$ 144,99'},
        {'name': 'Dona Dominga Reserva', 'price': 'R$ 69,99'},
    ],
    'total_visible': 3
}
ctx4 = build_image_context(caso4)
print(f"CONTEXTO:\n{ctx4}")
print(f"  Preco R$144,99: {'SIM' if '144,99' in ctx4 else 'NAO'}")
print(f"  Preco R$69,99: {'SIM' if '69,99' in ctx4 else 'NAO'}")

# ====== CASO 5: Screenshot sintetico ======
print("\n" + "=" * 70)
print("CASO 5 - Screenshot sintetico")
print("=" * 70)
caso5 = {
    'image_type': 'screenshot',
    'wines': [
        {'name': 'Wine A', 'price': 'R$ 99,99', 'rating': '4.2', 'source': 'vivino'},
        {'name': 'Wine B', 'price': 'R$ 149,99', 'rating': '3.9', 'source': 'wine.com'},
    ]
}
ctx5 = build_image_context(caso5)
print(f"CONTEXTO:\n{ctx5}")
print(f"  Precos: {'SIM' if '99,99' in ctx5 and '149,99' in ctx5 else 'NAO'}")
print(f"  Ratings: {'SIM' if '4.2' in ctx5 and '3.9' in ctx5 else 'NAO'}")
print(f"  Source vazou: {'FALHA' if 'vivino' in ctx5.lower() or 'wine.com' in ctx5.lower() else 'OK'}")

# ====== CASO 6: Batch misto ======
print("\n" + "=" * 70)
print("CASO 6 - Batch misto")
print("=" * 70)
caso6 = {
    'image_count': 3,
    'labels': [{'search_text': 'Pena Vermelha Reserva 2021 Tejo', 'ocr_result': {'price': 'R$ 89,99'}}],
    'screenshots': [{'wines': [{'name': 'Wine A', 'price': 'R$ 99,99', 'rating': '4.2', 'source': 'vivino'}]}],
    'shelves': [{'wines': [{'name': 'Perez Cruz LE', 'price': 'R$ 144,99'}, {'name': 'Dona Dominga', 'price': 'R$ 69,99'}], 'total_visible': 3}],
    'errors': []
}
ctx6 = build_batch_context(caso6)
print(f"CONTEXTO:\n{ctx6}")
print(f"  Label preco 89,99: {'SIM' if '89,99' in ctx6 else 'NAO'}")
print(f"  Screenshot preco 99,99: {'SIM' if '99,99' in ctx6 else 'NAO'}")
print(f"  Screenshot rating 4.2: {'SIM' if '4.2' in ctx6 else 'NAO'}")
print(f"  Shelf preco 144,99: {'SIM' if '144,99' in ctx6 else 'NAO'}")
print(f"  Source vazou: {'FALHA' if 'vivino' in ctx6.lower() else 'OK'}")
print(f"  Garrafas: {'FALHA' if 'garrafas' in ctx6.lower() else 'OK'}")

print("\n" + "=" * 70)
print("RESUMO NIVEL A — CONTEXTO")
print("=" * 70)
print("Todos os 6 casos testados com as funcoes CORRETAS (que deveriam estar em chat.py)")
print("ATENCAO: chat.py em disco esta REVERTIDO para pre-resolve. Estas funcoes NAO estao ativas.")
