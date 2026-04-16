# Catalogo Completo de Termos NOT_WINE (2026-04-15)

Data: 2026-04-15
Fonte: `C:\winegod-app\scripts\wine_filter.py` + `C:\winegod-app\scripts\pre_ingest_filter.py`
Total de termos regex: ~450
Total de regras procedurais: 6

Cada termo foi validado contra a base canonica Vivino (1.727.058 wines). Termos com
ratio (cauda/vivino) >= 10x foram incluidos. Termos com vivino >= 50 foram excluidos.

---

## PARTE A — Termos por regex (word-boundary, case-insensitive)

Cada linha = 1 termo. Formato: `termo` | lingua(s) | categoria

### A1. Destilados gerais (13 termos)

| # | termo | lingua | categoria |
|---|-------|--------|-----------|
| 1 | `whisky` | EN/global | destilado |
| 2 | `whiskey` | EN/IR | destilado |
| 3 | `vodka` | EN/global | destilado |
| 4 | `gin` (exceto ginger) | EN/global | destilado |
| 5 | `rum` | EN/global | destilado |
| 6 | `tequila` | EN/ES | destilado |
| 7 | `cognac` | FR/global | destilado |
| 8 | `bourbon` | EN | destilado |
| 9 | `mezcal` | ES | destilado |
| 10 | `aguardiente` | ES | destilado |
| 11 | `cachaca` / `cachaça` | PT | destilado |
| 12 | `sake` | JP/global | destilado |
| 13 | `soju` | KR | destilado |
| 14 | `grappa` | IT | destilado |
| 15 | `brandy` | EN/global | destilado |
| 16 | `absinth` | EN/DE | destilado |
| 17 | `schnapps` | EN/DE | destilado |
| 18 | `pisco` | ES | destilado |
| 19 | `armagnac` | FR | destilado |
| 20 | `rye` | EN | whisky tipo |
| 21 | `distillery` | EN | destilaria |
| 22 | `spirits` | EN | destilado generico |
| 23 | `rhum` | FR | rum frances |
| 24 | `negroni` | IT/global | drink |
| 25 | `bitters` | EN | mixer |
| 26 | `bacardi` | global | marca rum |

### A2. Destilarias escocesas de whisky (15 termos)

| # | termo | vivino | notas |
|---|-------|--------|-------|
| 27 | `glenmorangie` | 0 | Highland |
| 28 | `glenfarclas` | 0 | Speyside |
| 29 | `glenallachie` | 0 | Speyside |
| 30 | `bowmore` | 0 | Islay |
| 31 | `glendronach` | 0 | Highland |
| 32 | `mortlach` | 0 | Speyside |
| 33 | `glenrothes` | 0 | Speyside |
| 34 | `glenfiddich` | 0 | Speyside |
| 35 | `glenlivet` | 0 | Speyside |
| 36 | `macallan` | 0 | Speyside |
| 37 | `laphroaig` | 0 | Islay |
| 38 | `lagavulin` | 0 | Islay |
| 39 | `ardbeg` | 0 | Islay |
| 40 | `talisker` | 0 | Skye |
| 41 | `highland park` | 0 | Orkney |
| 42 | `macphail` | 0 | engarrafador |
| 43 | `glengoyne` | 0 | Highland |
| 44 | `benriach` | 0 | Speyside |
| 45 | `springbank` | 0 | Campbeltown |

### A3. Sake japones (4 termos)

| # | termo | vivino |
|---|-------|--------|
| 46 | `junmai` | 0 |
| 47 | `daiginjo` | 0 |
| 48 | `ginjo` | 0 |
| 49 | `nihonshu` | 0 |

### A4. Whisky context (3 termos)

| # | termo | vivino |
|---|-------|--------|
| 50 | `cask` | 246 (ratio 42x — whisky barrel aging) |
| 51 | `cask strength` | 0 |
| 52 | `single cask` | 62 (ratio 16x) |

### A5. Cerveja e sidra (11 termos)

| # | termo | lingua |
|---|-------|--------|
| 53 | `beer` | EN |
| 54 | `cerveja` | PT |
| 55 | `cerveza` | ES |
| 56 | `bier` | DE/NL |
| 57 | `birra` | IT |
| 58 | `cider` | EN |
| 59 | `sidra` | ES/PT |
| 60 | `weihenstephaner` | DE (marca) |
| 61 | `pils` | DE/EN (estilo) |
| 62 | `biere` | FR |
| 63 | `cans` | EN (latas) |
| 64 | `guinness` | global (marca) |

### A6. Bebidas nao-alcoolicas (19 termos)

| # | termo | lingua | tipo |
|---|-------|--------|------|
| 65 | `water` | EN | agua |
| 66 | `agua` | PT/ES | agua |
| 67 | `água` | PT | agua |
| 68 | `juice` | EN | suco |
| 69 | `suco` | PT | suco |
| 70 | `jugo` | ES | suco |
| 71 | `jus` | FR | suco |
| 72 | `soft drink` | EN | refrigerante |
| 73 | `soda` | EN | refrigerante |
| 74 | `refrigerante` | PT | refrigerante |
| 75 | `coffee` | EN | cafe |
| 76 | `café` / `cafe` | PT/FR/ES | cafe |
| 77 | `espresso` | IT/global | cafe |
| 78 | `nespresso` | global | marca |
| 79 | `kaffee` | DE | cafe |
| 80 | `tea` | EN | cha |
| 81 | `chá` / `cha` | PT | cha |
| 82 | `tee` | DE | cha |
| 83 | `infusion` | FR/EN | cha |
| 84 | `tisane` | FR | cha |

### A7. Licores (6 termos)

| # | termo | lingua |
|---|-------|--------|
| 85 | `giffard` | FR (marca) |
| 86 | `liqueur` | EN/FR |
| 87 | `liquor` | EN |
| 88 | `licor` | PT/ES |
| 89 | `likor` / `likoer` | DE |
| 90 | `liquore` | IT |

### A8. Comida — queijos (5 termos)

| # | termo | lingua |
|---|-------|--------|
| 91 | `cheese` | EN |
| 92 | `queijo` | PT |
| 93 | `fromage` | FR |
| 94 | `queso` | ES |
| 95 | `formaggio` | IT |
| 96 | `kase` | DE |

### A9. Comida — chocolate (6 termos)

| # | termo | lingua |
|---|-------|--------|
| 97 | `chocolate` | EN/PT/ES |
| 98 | `chocolat` | FR |
| 99 | `cacao` | ES/IT |
| 100 | `cocoa` | EN |
| 101 | `chokolade` | DK |
| 102 | `schokolade` | DE |
| 103 | `summerbird` | DK (marca) |

### A10. Comida — carnes e peixes (11 termos)

| # | termo | lingua |
|---|-------|--------|
| 104 | `chicken` | EN |
| 105 | `frango` | PT |
| 106 | `beef` | EN |
| 107 | `pork` | EN |
| 108 | `carne` | PT/ES |
| 109 | `fish` | EN |
| 110 | `shrimp` | EN |
| 111 | `salmon` | EN |
| 112 | `ham` | EN |
| 113 | `presunto` | PT |
| 114 | `prosciutto` | IT |

### A11. Comida — embutidos (5 termos)

| # | termo | lingua |
|---|-------|--------|
| 115 | `sausage` | EN |
| 116 | `linguica` | PT |
| 117 | `chorizo` | ES |
| 118 | `salame` | IT/PT |
| 119 | `salami` | EN/IT |

### A12. Comida — condimentos e molhos (8 termos)

| # | termo | lingua |
|---|-------|--------|
| 120 | `ketchup` | global |
| 121 | `mayonnaise` | EN/FR |
| 122 | `mustard` | EN |
| 123 | `vinegar` | EN |
| 124 | `olive oil` | EN |
| 125 | `azeite` | PT |
| 126 | `aceite` | ES |
| 127 | `sauce` | EN/FR |
| 128 | `molho` | PT |
| 129 | `salsa` | ES/IT |

### A13. Comida — doces e conservas (6 termos)

| # | termo | lingua |
|---|-------|--------|
| 130 | `honey` | EN |
| 131 | `mel` | PT |
| 132 | `miel` | ES |
| 133 | `jam` | EN |
| 134 | `geleia` | PT |
| 135 | `mermelada` | ES |

### A14. Comida — massas, graos, cereais (10 termos)

| # | termo | lingua |
|---|-------|--------|
| 136 | `pasta` | EN/IT |
| 137 | `noodle` | EN |
| 138 | `macarrao` / `macarrão` | PT |
| 139 | `rice` | EN |
| 140 | `arroz` | PT/ES |
| 141 | `riz` | FR |
| 142 | `cereal` | EN/PT/ES |
| 143 | `granola` | global |
| 144 | `aveia` | PT |
| 145 | `oats` | EN |

### A15. Comida — snacks (3 termos)

| # | termo | lingua |
|---|-------|--------|
| 146 | `snack` | EN |
| 147 | `chips` | EN |
| 148 | `crisp` | EN |

### A16. Comida — dieta (3 termos)

| # | termo | lingua |
|---|-------|--------|
| 149 | `glutenfri` | DK/SV |
| 150 | `gluten` | EN/global |
| 151 | `kulinarne` | PL (culinario) |

### A17. Gift cards e vouchers (5 termos)

| # | termo | lingua |
|---|-------|--------|
| 152 | `gift card` | EN |
| 153 | `gutschein` | DE |
| 154 | `carte cadeau` | FR |
| 155 | `tarjeta regalo` | ES |
| 156 | `voucher` | EN/global |

### A18. Acessorios de vinho (15 termos)

| # | termo | lingua |
|---|-------|--------|
| 157 | `corkscrew` | EN |
| 158 | `saca-rolha` | PT |
| 159 | `decanter` | EN |
| 160 | `wine rack` | EN |
| 161 | `wine cooler` | EN |
| 162 | `wine fridge` | EN |
| 163 | `wine opener` | EN |
| 164 | `bottle opener` | EN |
| 165 | `abridor` | PT |
| 166 | `wine glass` | EN |
| 167 | `goblet` | EN |
| 168 | `tumbler` | EN |
| 169 | `taca` / `taça` | PT |
| 170 | `zalto` | global (marca taca) |
| 171 | `yaxell` | global (marca faca) |
| 172 | `maileg` | DK (marca brinquedo) |
| 173 | `glas` | DE (copo) |
| 174 | `rack` | EN (suporte) |

### A19. Higiene e beleza (17 termos)

| # | termo | lingua |
|---|-------|--------|
| 175 | `soap` | EN |
| 176 | `sabonete` | PT |
| 177 | `jabon` | ES |
| 178 | `shampoo` | global |
| 179 | `conditioner` / `condicionador` | EN/PT |
| 180 | `perfume` | global |
| 181 | `fragrance` | EN |
| 182 | `cologne` | EN |
| 183 | `cream` | EN |
| 184 | `creme` | PT/FR |
| 185 | `lotion` | EN |
| 186 | `moisturizer` | EN |
| 187 | `toothpaste` | EN |
| 188 | `mouthwash` | EN |
| 189 | `razor` | EN |
| 190 | `deodorant` | EN |
| 191 | `detergent` / `detergente` | EN/PT |
| 192 | `suavizante` | ES (amaciante) |
| 193 | `esponja` | ES/PT |
| 194 | `escova` | PT |
| 195 | `toilet paper` / `papel higienico` | EN/PT |

### A20. Decoracao (10 termos)

| # | termo | lingua |
|---|-------|--------|
| 196 | `candle` | EN |
| 197 | `vela` | PT/ES |
| 198 | `candela` | IT |
| 199 | `bougie` | FR |
| 200 | `neon sign` | EN |
| 201 | `quadro` | PT |
| 202 | `poster` | EN |
| 203 | `flower` | EN |
| 204 | `flor` | PT/ES |
| 205 | `bouquet` | FR/EN |
| 206 | `flores` | PT/ES |
| 207 | `lampara` | ES |

### A21. Vestuario (15 termos)

| # | termo | lingua |
|---|-------|--------|
| 208 | `t-shirt` | EN |
| 209 | `camiseta` | PT/ES |
| 210 | `shirt` | EN |
| 211 | `jeans` | global |
| 212 | `bra` | EN |
| 213 | `panties` | EN |
| 214 | `lingerie` | FR/EN |
| 215 | `underwear` | EN |
| 216 | `dress` | EN |
| 217 | `vestido` | PT/ES |
| 218 | `hoodie` | EN |
| 219 | `blouse` | EN/FR |
| 220 | `blusa` | PT |
| 221 | `roupas` | PT |
| 222 | `zapatillas` | ES (sapatos) |

### A22. Esportes (4 termos)

| # | termo | lingua |
|---|-------|--------|
| 223 | `volleyball` | EN |
| 224 | `basketball` | EN |
| 225 | `soccer` | EN |
| 226 | `dumbbell` | EN |

### A23. Pet (4 termos)

| # | termo | lingua |
|---|-------|--------|
| 227 | `pet food` | EN |
| 228 | `dog food` | EN |
| 229 | `cat food` | EN |
| 230 | `ração` | PT |

### A24. Livros e brinquedos (6 termos)

| # | termo | lingua |
|---|-------|--------|
| 231 | `book` | EN |
| 232 | `livro` | PT |
| 233 | `libro` | ES/IT |
| 234 | `livre` | FR |
| 235 | `toy` | EN |
| 236 | `brinquedo` | PT |
| 237 | `juguete` | ES |

### A25. Eletronicos (8 termos)

| # | termo | lingua |
|---|-------|--------|
| 238 | `laptop` | global |
| 239 | `smartphone` | global |
| 240 | `iphone` | global |
| 241 | `headphone` | EN |
| 242 | `speaker` | EN |
| 243 | `television` | EN |
| 244 | `xiaomi` | global (marca) |
| 245 | `led` | global |

### A26. Eletrodomesticos (5 termos)

| # | termo | lingua |
|---|-------|--------|
| 246 | `espresso machine` | EN |
| 247 | `coffee machine` / `coffee maker` | EN |
| 248 | `grinder` | EN |
| 249 | `moedor` | PT |
| 250 | `gillette` | global (marca) |
| 251 | `temptech` | global (marca adega) |

### A27. Kits, caixas, packs — EN (11 termos)

| # | termo | lingua |
|---|-------|--------|
| 252 | `box` | EN |
| 253 | `kit` | EN/global |
| 254 | `bundle` | EN |
| 255 | `dozen` | EN |
| 256 | `mixed case` | EN |
| 257 | `case of N` (N=digito) | EN |
| 258 | `subscription` | EN |
| 259 | `advent calendar` | EN |
| 260 | `owc` (original wooden case) | EN |
| 261 | `outlet` | EN |
| 262 | `tray` | EN |

### A28. Kits, caixas, packs — ES (9 termos)

| # | termo | lingua |
|---|-------|--------|
| 263 | `caja` | ES |
| 264 | `cajita` | ES |
| 265 | `estuche` | ES |
| 266 | `canastas` | ES |
| 267 | `navidenas` / `navideñas` | ES |
| 268 | `ancheta` | ES |
| 269 | `anteojos` | ES (oculos) |
| 270 | `llavero` | ES (chaveiro) |
| 271 | `juego` | ES (jogo/kit) |

### A29. Kits, caixas, packs — PT (4 termos)

| # | termo | lingua |
|---|-------|--------|
| 272 | `caixa` | PT |
| 273 | `garrafas` | PT |
| 274 | `unidades` | PT |
| 275 | `lata` | PT/ES |

### A30. Kits, caixas, packs — IT (5 termos)

| # | termo | lingua |
|---|-------|--------|
| 276 | `cassetta` | IT |
| 277 | `astuccio` | IT |
| 278 | `astucciato` | IT |
| 279 | `scatola` | IT |
| 280 | `confezione` | IT |

### A31. Kits, caixas, packs — FR (1 termo)

| # | termo | lingua |
|---|-------|--------|
| 281 | `coffret` | FR |

### A32. Kits, caixas — DE (2 termos)

| # | termo | lingua |
|---|-------|--------|
| 282 | `personliche` | DE (pessoal) |
| 283 | `empfehlung` | DE (recomendacao) |

### A33. Kits, caixas — NL (6 termos)

| # | termo | lingua |
|---|-------|--------|
| 284 | `persoonlijke` | NL (pessoal) |
| 285 | `aanbeveling` | NL (recomendacao) |
| 286 | `flessen` | NL (garrafas) |
| 287 | `stuks` | NL (pecas) |
| 288 | `fles` | NL (garrafa) |
| 289 | `doos` | NL (caixa) |

### A34. Kits, caixas — DK (4 termos)

| # | termo | lingua |
|---|-------|--------|
| 290 | `gavekurv` | DK (cesta presente) |
| 291 | `flasker` | DK (garrafas) |
| 292 | `smagekasse` | DK (caixa degustacao) |
| 293 | `gave` | DK (presente) |
| 294 | `kologiske` | DK (organico) |

### A35. Kits, caixas — PL (4 termos)

| # | termo | lingua |
|---|-------|--------|
| 295 | `warsztaty` | PL (workshops) |
| 296 | `wytrawne` | PL (seco/generico) |
| 297 | `personalizacji` | PL (personalizacao) |
| 298 | `zestaw` | PL (conjunto) |

### A36. Kits, caixas — RO (1 termo)

| # | termo | lingua |
|---|-------|--------|
| 299 | `sticle` | RO (garrafas) |

### A37. Estado e siglas (7 termos)

| # | termo | lingua |
|---|-------|--------|
| 300 | `damaged` | EN |
| 301 | `arrival` | EN |
| 302 | `beige` | FR/EN (cor) |
| 303 | `ltr` | global (litro sigla) |
| 304 | `pcs` | global (pieces) |
| 305 | `mlt` | global (mililitro sigla) |

---

## PARTE B — Regras procedurais (logica no codigo, nao regex simples)

Implementadas em `scripts/pre_ingest_filter.py`.

### B1. ABV fora de 10-15%

```
Regex: (\d+(?:[.,]\d+)?)\s*%\s*abv
Regra: se o valor numerico e < 10% ou > 15%, e NOT_WINE
Justificativa: vinhos tipicos tem ABV entre 10% e 15%. Abaixo = cerveja/suco.
Acima = destilado/licor. Excepcoes raras (Moscato 5%, Porto 20%) sao aceitas
como trade-off.
```

### B2. Volume nao-padrao

```
Regex: (\d+(?:[.,]\d+)?)\s*(ml|cl|l|oz)
Regra: aceitar APENAS 750ml, 0.75L, 75cl, 1.5L, 375ml, 500ml, 3L, 1L
Qualquer outro volume (100ml, 200ml, 330ml, 4oz, 5oz, 50cl, 10L) = NOT_WINE
Justificativa: vinhos sao vendidos em formatos padrao. Volumes fora indicam
cerveja (330ml), miniatura (50ml), galao (5L), cosmetico (100ml), etc.
```

### B3. Gramatura

```
Regex: \d+(?:[.,]\d+)?\s*(g|gr|grs|kg|gram|gramm|grams|grammes)
Regra: se o nome tem peso em gramas ou quilos, e NOT_WINE
Justificativa: vinho nao se pesa. Gramas = alimento (queijo 300g, chocolate 200g).
```

### B4. Data com sufixo ordinal

```
Regex: \d+(st|nd|rd|th)
Regra: se o nome tem numero + sufixo ordinal ingles, e NOT_WINE
Justificativa: indica evento ("Thursday 20th May Wine Tasting"), nao produto.
Excepcao rara: "4th Generation" (nome de vinho). Trade-off aceito.
```

### B5. Case com numero > 1

```
Regex: case|caisse + numero adjacente entre 2 e 96
Regra: se o nome tem "case" ou "caisse" junto de um numero > 1, e NOT_WINE (kit)
Numeros 2-96 = quantidade de garrafas. Exclui safras (1900+).
Se "case" aparece sem numero (ex: "Case ()", "Case only") = NAO bloqueia.
```

### B6. Nome vazio ou curto

```
Regra: se len(nome.strip()) < 3, e NOT_WINE
Justificativa: produto sem nome nao e classificavel como vinho.
```

---

## PARTE C — Termos investigados e EXCLUIDOS (nao usar)

Estes termos foram validados mas **rejeitados** por causa de vivino alto (falso
positivo real) ou ambiguidade:

| termo | cauda | vivino | ratio | motivo da exclusao |
|-------|-------|--------|-------|--------------------|
| `ser` (PL queijo) | 396 | 77 | 12.8x | muito curto, bate em "Reserve" |
| `flowers` | 370 | 77 | 12.0x | "Flowers Vineyards" produtor californiano |
| `verre` (FR copo) | 316 | 50 | 15.7x | "verre de vin" em nomes vinicolas |
| `blue` | 2.270 | 1.076 | 4.7x | "Blue Nun" wine; "Blue Label" whisky |
| `blend` | 5.918 | 16.457 | 0.8x | "wine blend" e legitimamente vinicola |
| `sparkling` | 3.438 | 7.550 | 1.0x | "sparkling wine" e valido |
| `premium` | 2.801 | 6.507 | 1.0x | marketing generico, vinho real usa |
| `magnum` | 6.726 | 81 | 184x | ratio alto mas "Magnum 1.5L" e formato real de vinho |
| `year old` | 4.277 | 999 | 9.5x | "10 Year Old Tawny Port" e wine real |
| `caisse` (FR caixa) | 115 | 12 | 23.8x | "caisse bois" e formato de Bordeaux premium |

---

## Nota final

Este catalogo reflete o estado de 2026-04-15. A fonte de verdade executavel e
sempre `scripts/wine_filter.py` + `scripts/pre_ingest_filter.py`. Se novos termos
forem adicionados, atualizar este catalogo junto.
