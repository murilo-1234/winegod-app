"""
Filtro centralizado de não-vinhos.

Detecta produtos que NÃO são vinho por nome/URL.
Usado como pré-filtro antes do LLM e como validação pós-import.

Categorias cobertas:
- Comida (queijo, chocolate, carne, condimentos, grãos, frutas)
- Destilados (whisky, vodka, bourbon, gin, rum, tequila, cognac, cachaça)
- Cervejas e sidras
- Bebidas não-alcoólicas (água, suco, refrigerante, café, chá)
- Acessórios de vinho (taça, saca-rolha, decanter)
- Higiene pessoal (sabonete, shampoo, perfume, creme)
- Decoração (vela, quadro, neon)
- Vestuário (camiseta, lingerie)
- Eletrônicos e eletrodomésticos
- Gift cards e vouchers
- Animais/pet food
- Livros, brinquedos, flores
- Material de limpeza
"""

import re

# Regex com word boundaries para evitar falsos positivos.
# Ex: "gin" não matcha "ginger" graças ao negative lookahead.
NON_WINE_RE = re.compile(
    r'\b('
    # --- Destilados ---
    r'whisky|whiskey|vodka|gin(?!\s*ger)|rum\b|tequila|cognac|bourbon|'
    r'mezcal|aguardiente|cachaca|cachaça|sake|soju|grappa|brandy|'
    r'absinth|schnapps|pisco|armagnac|'

    # --- Cerveja e sidra ---
    r'beer|cerveja|cerveza|bier|birra|cider|sidra|'

    # --- Bebidas não-alcoólicas ---
    r'water\b|agua\b|água|juice|suco|jugo|jus\b|'
    r'soft[\s-]?drink|soda\b|refrigerante|'
    r'coffee|café|cafe\b|espresso|nespresso|kaffee|'
    r'tea\b|chá|cha\b|infusion|tisane|'

    # --- Comida ---
    r'cheese|queijo|fromage|queso|formaggio|'
    r'chocolate|chocolat|cacao|cocoa|'
    r'chicken|frango|beef|pork|carne|fish\b|shrimp|salmon|'
    r'ketchup|mayonnaise|mustard|vinegar|'
    r'olive[\s-]?oil|azeite|aceite|'
    r'honey|mel\b|miel|jam\b|geleia|mermelada|'
    r'sauce\b|molho|salsa\b|'
    r'pasta\b|noodle|macarrao|macarrão|rice\b|arroz|riz\b|'
    r'cereal|granola|aveia|oats|'
    r'ham\b|presunto|prosciutto|'
    r'snack|chips\b|crisp|'

    # --- Gift cards e vouchers ---
    r'gift[\s-]?card|gutschein|carte[\s-]?cadeau|tarjeta[\s-]?regalo|voucher|'

    # --- Acessórios de vinho ---
    r'corkscrew|saca[\s-]?rolha|decanter|wine[\s-]?rack|'
    r'wine[\s-]?cooler|wine[\s-]?fridge|wine[\s-]?opener|'
    r'bottle[\s-]?opener|abridor|'

    # --- Taças e copos (cuidado: "copa" pode ser região) ---
    r'wine[\s-]?glass|goblet|tumbler|'
    r'taca\b|taça|'

    # --- Higiene e beleza ---
    r'soap|sabonete|jabon|'
    r'shampoo|conditioner|condicionador|'
    r'perfume|fragrance|cologne|'
    r'cream\b|creme\b|lotion|moisturizer|'
    r'toothpaste|mouthwash|razor|deodorant|'
    r'detergent|detergente|'
    r'toilet[\s-]?paper|papel[\s-]?higienico|'

    # --- Decoração ---
    r'candle|vela\b|candela|bougie|'
    r'neon[\s-]?sign|quadro|poster\b|'
    r'flower|flor\b|bouquet|flores\b|'

    # --- Vestuário ---
    r't[\s-]?shirt|camiseta|shirt\b|jeans|'
    r'bra\b|panties|lingerie|underwear|'
    r'dress\b|vestido|hoodie|'

    # --- Esportes ---
    r'volleyball|basketball|soccer|dumbbell|'

    # --- Pet ---
    r'pet[\s-]?food|dog[\s-]?food|cat[\s-]?food|ração|'

    # --- Livros e brinquedos ---
    r'book\b|livro|libro|livre\b|'
    r'toy\b|brinquedo|juguete|'

    # --- Eletrônicos ---
    r'laptop|smartphone|iphone|headphone|speaker\b|television|'

    # --- Eletrodomésticos ---
    r'espresso[\s-]?machine|coffee[\s-]?machine|coffee[\s-]?maker|'
    r'grinder|moedor'

    r')\b',
    re.IGNORECASE
)


def is_wine(nome):
    """Retorna True se o produto provavelmente é vinho. False se é não-vinho."""
    if not nome or len(nome.strip()) < 3:
        return False
    return not NON_WINE_RE.search(nome)


def classify_product(nome):
    """Retorna ('wine', None) ou ('not_wine', 'categoria detectada')."""
    if not nome or len(nome.strip()) < 3:
        return 'not_wine', 'nome_vazio_ou_curto'

    match = NON_WINE_RE.search(nome)
    if match:
        return 'not_wine', match.group(0).lower()

    return 'wine', None


# ============================================================
# Teste rápido
# ============================================================

if __name__ == "__main__":
    # Casos que DEVEM ser filtrados (não-vinho)
    should_block = [
        "Johnnie Walker Black Label Whisky 750ml",
        "Lindt Excellence Dark Chocolate 85%",
        "Nespresso Vertuo Coffee Capsules",
        "Yankee Candle Autumn Leaves Large",
        "Victoria's Secret Lingerie Set",
        "KitchenAid Espresso Machine Pro",
        "Gift Card R$100",
        "Queijo Brie Président 200g",
        "Chicken Breast Organic 1kg",
        "Samsung Galaxy S24 Smartphone",
        "Racao Premium Dog Food 15kg",
        "Bombay Sapphire Gin 750ml",
        "Jack Daniel's Bourbon Tennessee",
        "Heineken Beer 355ml Pack",
        "Taça Cristal Bohemia 450ml",
        "Saca-Rolha Profissional Inox",
        "Volleyball Mikasa V200W",
        "Vela Aromática Lavanda 300g",
    ]

    # Casos que NÃO devem ser filtrados (vinho real)
    should_pass = [
        "Château Margaux 2015 Premier Grand Cru",
        "Casillero del Diablo Cabernet Sauvignon 2022",
        "Penfolds Grange Shiraz 2018",
        "Dom Pérignon Vintage 2013",
        "Malbec Reserva Catena Zapata 2020",
        "Vinho Verde Aveleda Fonte",
        "Brunello di Montalcino 2017 Biondi Santi",
        "Riesling Spätlese Dr. Loosen 2021",
        "Amarone della Valpolicella Classico 2016",
        "Prosecco Extra Dry Mionetto",
    ]

    print("=== DEVEM SER BLOQUEADOS (não-vinho) ===")
    for nome in should_block:
        result, cat = classify_product(nome)
        status = "OK BLOQUEADO" if result == 'not_wine' else "FALHA - passou!"
        print(f"  [{status}] {nome} => {cat}")

    print("\n=== DEVEM PASSAR (vinho) ===")
    for nome in should_pass:
        result, cat = classify_product(nome)
        status = "OK PASSOU" if result == 'wine' else f"FALHA - bloqueado por '{cat}'!"
        print(f"  [{status}] {nome}")
