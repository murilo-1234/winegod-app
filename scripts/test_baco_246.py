"""
Script para testar o Baco com 246 perguntas curadas.
Chama a API de producao e grava todas as respostas.

Uso: python scripts/test_baco_246.py
Saida: scripts/baco_test_results_246.md
"""

import requests
import uuid
import time
import json
import re
import sys

API_URL = "https://winegod-app.onrender.com/api/chat"
GUEST_LIMIT = 5  # mensagens por session_id
DELAY_BETWEEN = 2  # segundos entre requests
OUTPUT_FILE = "scripts/baco_test_results_246.md"

# ---------------------------------------------------------------------------
# 246 perguntas curadas (extraidas de PERGUNTAS_CURADAS_BACO.md)
# ---------------------------------------------------------------------------
PERGUNTAS = [
    # A — INICIANTE / CONHECIMENTO BASICO (35)
    "qual a diferenca entre vinho seco e suave?",
    "tinto vai na geladeira ou estraga?",
    "vinho barato da dor de cabeca mesmo ou eh mito?",
    "como eu sei se um vinho eh bom sem pagar caro?",
    "o que eh tanino? sinto uma sensacao de boca seca e nao sei se eh defeito",
    "vinho com tampa de rosca eh pior mesmo?",
    "quantas tacas da pra servir numa garrafa de 750 ml?",
    "qual a diferenca entre vinho de mesa e vinho fino?",
    "vinho de caixinha presta pra cozinhar ou da pra beber de boa?",
    "oq significa corpo do vinho? como saber se eh encorpado?",
    "o que eh decantar e quando vale fazer isso?",
    "como saber se o vinho estragou?",
    "o que sao sulfitos e por que colocam no vinho?",
    "qual a diferenca de reserva, gran reserva e reserva privada?",
    "o que quer dizer DOC, DOCG e AOC no rotulo?",
    "me explica o significado de terroir de um jeito que eu entenda na pratica",
    "o que eh assemblage no vinho?",
    "o que eh um vinho varietal?",
    "qual a diferenca entre vinho organico e biodinamico?",
    "o que eh vinho natural? eh igual a organico?",
    "o que eh um vinho de guarda?",
    "vinho envelhece sempre ficando melhor ou nao?",
    "qual a temperatura ideal pra servir tinto e branco?",
    "como ler um rotulo de vinho frances? nao entendo nada",
    "o que eh garrafeira num vinho portugues?",
    "brut vs demi-sec, qual eh menos doce?",
    "champagne vs prosecco vs cava, qual a diferenca real?",
    "o que eh vinho laranja (orange wine)?",
    "existe vinho vegano?",
    "existe vinho sem alcool que realmente pareca vinho?",
    "por que vinho da caixa eh tao desprezado?",
    "rose eh vinho de mulher ou isso eh bobagem?",
    "por que vinho caro as vezes parece pior pra quem ta comecando?",
    "Syrah e Shiraz sao a mesma uva ou muda alguma coisa?",
    "o que significa premio no rotulo? eh confiavel?",

    # B — ENTUSIASTA CASUAL (12)
    "malbec argentino bom ate 80 reais?",
    "por que Pinot Noir costuma ser mais caro que os outros?",
    "entre Casillero del Diablo e Reservado da Concha y Toro, qual vale mais a pena?",
    "tem algum vinho tipo o Pergola mas melhorzinho pra levar num jantar?",
    "qual a diferenca real entre um vinho reserva e um reservado?",
    "vale a pena comprar vinho em supermercado ou so tem coisa ruim?",
    "qual regiao do Chile tem os melhores Carmenere?",
    "O Leyda Single Vineyard Garuma eh muito superior ao reserva comum deles?",
    "qual vinho tinto mais facil de beber pra quem ta comecando?",
    "tem algum Malbec argentino bom que custa menos de 60 reais?",
    "Bordeaux ou Rioja, qual eh mais encorpado?",
    "indica um vinho branco bom pro calor de SC?",

    # C — EXPERT / COLECIONADOR (15)
    "comparar safras 2015 vs 2018 de Barolo, qual entregou mais equilibrio?",
    "qual a nota e a faixa de preco do Opus One 2019?",
    "Sassicaia 2020 ou Tignanello 2021, qual esta mais consistente?",
    "quantos vinhos de Chablis Premier Cru voces tem cadastrados e qual a media de nota?",
    "qual a diferenca entre um Grand Cru e um Premier Cru?",
    "faz sentido comprar Brunello 2017 agora ou esperar mais?",
    "alguem comparou Vega Sicilia Unico com Pingus em custo-beneficio?",
    "meu palate ainda nao pegou Brett direito, como diferenciar defeito de estilo?",
    "Acabei de abrir um Barolo 2015 e ta super tannico, precisa decantar quanto tempo?",
    "qual o potencial de guarda do Vega Sicilia?",
    "comprei uma caixa de Bordeaux 2016 em promocao, quanto tempo aguenta em adega simples?",
    "me fala as notas de degustacao do Catena Zapata Malbec Argentino 2020",
    "quantos vinhos da Duckhorn tem cadastrados?",
    "tem como ver a evolucao de preco do Chateau Margaux 2000?",
    "por que Amarone della Valpolicella eh tao caro se parece um tinto comum?",

    # D — PRESENTEADOR (8)
    "vinho pra dar de presente de aniversario ate 200 reais, algo elegante",
    "quero uma garrafa chique pra sogra, mas que nao seja cara demais",
    "presente pra chefe que gosta de vinho, espumante ou tinto?",
    "vinho romantico pra dar de presente pro casal",
    "presente de natal pra chefe homem que gosta de Bordeaux mas nao entendo nada disso",
    "garrafa elegante pra sogra que aprecia vinho do Porto",
    "vinho bom pra presente de casamento, pode ser ate 500 reais",
    "vinho pra dar de presente de aniversario de 40 anos pra um cara que gosta de vinho",

    # E — PROFISSIONAL / RESTAURANTE (8)
    "tintos italianos pra montar carta entre 80 e 150 reais, o que vale olhar?",
    "espumante brasileiro bom pra evento corporativo de 200 pessoas",
    "me ve 5 opcoes de brancos leves com margem boa pra restaurante de frutos do mar",
    "sugestao de Prosecco pra by the glass com boa margem de lucro",
    "preciso de um branco que agrade todo mundo pra menu executivo",
    "vinhos por taca pra restaurante movimentado, o que funciona?",
    "qual vinho italiano pra colocar na carta de um restaurante novo?",
    "espumante brasileiro custo-beneficio pra evento de 100 pessoas, orcamento medio",

    # F — VIAJANTE (8)
    "vou pra Mendoza, o que eu preciso provar la sem cair so no obvio?",
    "trouxe um vinho da Toscana chamado Banfi Chianti Classico, ele eh bom mesmo?",
    "na Serra Gaucha, quais vinicolas valem visita se eu curto espumante?",
    "quais vinhos portugueses sao imperdiveis em uma viagem ao Douro?",
    "melhores vinhos pra comprar em viagem pro Chile",
    "achei esse vinho em Portugal chamado Barca Velha, vale trazer pro Brasil?",
    "voltei do Chile e comprei um Almaviva, fiz boa escolha?",
    "esse vinho que comprei em Portugal, Herdade do Esporao, combina com qual comida?",

    # G — NO SUPERMERCADO (12)
    "to no mercado agora, pego esse Cabernet chileno de 39 ou esse Merlot de 44?",
    "esse Santa Helena Reservado presta ou eh cilada?",
    "no supermercado, qual pista no rotulo mostra que o vinho vai ser mais encorpado?",
    "to no Pao de Acucar, o Periquita reserva ta 60 reais, vale a pena?",
    "esse Benjamin Nieto Senetiner eh bom ou eh muito basico?",
    "to na duvida entre o Toro Loco e o Casillero del Diablo aqui no mercado",
    "tem algum rose gelado aqui no Carrefour que seja refrescante?",
    "Porto Carras de 45 reais aqui no Pao de Acucar eh bom?",
    "rotulo da Freixenet preto ou rosa, qual levar?",
    "entre o Trivento e o Trapiche qual escolher por 35 reais?",
    "vi um vinho nacional Salton por 25 reais, eh drinkable?",
    "to no Carrefour e achei um vinho chamado 1865, compro?",

    # H — NO RESTAURANTE (10)
    "to no restaurante e a carta so tem nomes que eu nao conheco, como escolho sem passar vergonha?",
    "entre Carmenere e Malbec, qual combina mais com bife ancho?",
    "esse vinho da casa costuma ser furada ou depende?",
    "tirei foto da carta do restaurante, qual dessas opcoes tem melhor custo-beneficio?",
    "vale pedir taca ou garrafa nesse caso?",
    "o sommelier indicou um Brunello di Montalcino por 350, ta caro ou fair price?",
    "champanhe na adega ta 600 reais, mesma garrafa eh 450 na internet, pago ou peco outro?",
    "o garcom trouxe um vinho pra provar, como agir se nao gostei?",
    "to num japones, qual vinho combina com sushi?",
    "qual a diferenca desse Chianti pro Valpolicella que estao no menu?",

    # I — CHURRASCO / JANTAR EM CASA (12)
    "vinho pra churrasco de picanha e linguica, orcamento ate 70 reais?",
    "vou fazer massa ao molho branco com frango, qual vinho fica melhor?",
    "pra sushi em casa eh melhor Sauvignon Blanc, Riesling ou espumante?",
    "vinho tinto encorpado pra harmonizar com costela no bafo, 60 a 100 reais",
    "sobremesa com chocolate pede vinho qual sem ficar enjoativo?",
    "vou fazer noite de queijos e vinhos em casa, o que comprar pra nao errar?",
    "vinho tinto combina com peixe assado ou fica ruim?",
    "qual vinho levar num jantar na casa de amigos que eu nao conheco o gosto?",
    "jantar romantico em casa, vinho tinto ou branco?",
    "vou fazer fondue, que vinho serve junto?",
    "feijoada combina com vinho? qual?",
    "churrasco com amigos, preciso de 3 garrafas, total 150 reais, o que levar?",

    # J — HARMONIZACAO ESPECIFICA (15)
    "qual tipo de vinho combina com sushi e sashimi?",
    "vinho pra acompanhar pizza de pepperoni?",
    "vinho portugues bom pra harmonizar com bacalhau?",
    "vinho pra harmonizar com queijo gorgonzola",
    "vinho pra harmonizar com chocolate amargo 70%",
    "sugestao de vinho pra piquenique no parque com frios",
    "que vinho combina com fondue de queijo classico?",
    "vinho espanhol bom pra servir com paella?",
    "vinho italiano bom pra harmonizar com massa ao pesto?",
    "Pinot Grigio ou Chardonnay pra risoto de camarao?",
    "jantar vegetariano com berinjela a parmegiana, qual vinho?",
    "moqueca pede qual tipo de vinho?",
    "vinho pra acompanhar salmon grelhado?",
    "qual vinho pra tomar com queijo brie?",
    "vinho sugerido com cordeiro tem tanino forte, vou gostar se prefiro leve?",

    # K — COMPRANDO ONLINE (8)
    "to vendo um Freixenet Prosecco e um Chandon Brut online, qual compensa mais?",
    "esse vinho ta com desconto de 40%, eh promocao boa ou preco maquiado?",
    "comparando no Wine.com.br o Terrazas Reserva vs Norton Privada, qual melhor?",
    "vale a pena comprar Kit Casillero del Diablo com 20% off ou eh enganacao?",
    "frete de vinho estraga a garrafa no calor?",
    "qual loja online mais barata pra comprar vinho no Brasil?",
    "vi um Porto 10 anos online, mas nunca bebi, eh muito doce?",
    "achei um vinho com 93 pontos Robert Parker por 99 reais, eh confiavel?",

    # L — REDES SOCIAIS / VIRAL (12)
    "vi no Instagram falarem super bem do JP Chenet, ele eh bom ou eh mais marketing?",
    "aquele vinho Juliette que viralizou presta?",
    "alguem postou foto de um Whispering Angel, esse rose eh tudo isso?",
    "vi um video falando que vinho laranja eh modinha, faz sentido?",
    "esse vinho de lata que tao postando muito presta ou eh so marketing?",
    "no TikTok vi um vinho azul, isso existe? eh bom?",
    "vi no Instagram um vinho com rotulo de ovelha, parece ser australiano",
    "vi uma foto de um vinho chamado The Prisoner, o que eh isso?",
    "no reels vi um cara falando de Caymus, eh realmente especial?",
    "todo mundo ta falando de vinho do Libano no Twitter, tem algum bom?",
    "vi um TikTok dizendo que vinho de 30 reais eh igual de 300, eh verdade?",
    "aquele vinho que o Galvao Bueno faz eh bom ou eh so marketing?",

    # M — CUSTO-BENEFICIO (12)
    "melhor vinho tinto ate 50 reais?",
    "melhor Pinot Noir ate 120 reais no Brasil?",
    "melhor espumante brut ate 90 reais?",
    "melhor vinho portugues ate 80 conto?",
    "melhor custo-beneficio pra quem quer comecar a beber vinho?",
    "top 5 vinhos malbec argentinos com melhor custo-beneficio",
    "melhor cabernet sauvignon ate 100 reais no Brasil",
    "melhor espumante nacional ate 40 reais",
    "qual champanhe custo-beneficio ate 300 reais?",
    "melhor vinho brasileiro espumante na faixa dos 150 reais",
    "melhor vinho branco seco ate 40 reais",
    "melhor vinho pra iniciante ate 35 reais",

    # N — COMPARACOES (12)
    "Malbec vs Cabernet Sauvignon, qual eh mais encorpado?",
    "Malbec vs Carmenere, qual mais frutado?",
    "Cabernet Sauvignon do Chile vs do Brasil, qual ganha?",
    "Pinot Noir da Borgonha vs Napa Valley",
    "Pinot Noir do Brasil vs do Chile, qual eh melhor?",
    "Tannat uruguaio vs Tannat brasileiro, tem diferenca?",
    "Carmenere vs Merlot, qual mais suave?",
    "vinho chileno ou argentino, qual costuma valer mais pelo preco?",
    "vale mais comprar vinho do novo mundo ou do velho mundo por 100 reais?",
    "Chablis vs Sauvignon Blanc da Nova Zelandia pra frutos do mar?",
    "Miolo Selecao ou Salton Paradoxo, qual entrega mais?",
    "Catena Malbec ou DV Catena, qual vale mais?",

    # O — RANKINGS / LISTAS (10)
    "top 10 vinhos bons e baratos pra comprar hoje",
    "ranking dos melhores Malbec ate 100 reais",
    "quais sao os Pinot Noir mais bem avaliados abaixo de 200 reais?",
    "quais sao os 5 vinhos com maior nota entre os que custam menos de 150 reais?",
    "top 10 vinhos brasileiros",
    "ranking dos melhores Proseccos ate 80 reais",
    "quais os 3 melhores Cabernet Sauvignon do mundo segundo o sistema?",
    "lista de vinhos premiados da Campanha Gaucha",
    "quais sao os melhores vinhos de entrada pra quem ta comecando?",
    "top 5 vinicolas da Serra Gaucha",

    # P — ESTATISTICAS / DADOS (10)
    "quantos vinhos argentinos tem no banco de dados?",
    "qual pais tem mais vinicolas cadastradas?",
    "qual a media de nota dos vinhos brasileiros?",
    "quantos vinhos tem nota acima de 90 pontos?",
    "qual vinicola brasileira tem mais vinhos no sistema?",
    "qual a media de preco dos tintos chilenos?",
    "qual regiao da Espanha tem melhor media de nota pelo preco?",
    "quantos vinhos no total voce tem cadastrado?",
    "qual a uva mais popular no seu sistema?",
    "qual a nota media dos vinhos portugueses vs chilenos no sistema?",

    # Q — FOTO / OCR (10)
    "tirei foto desse rotulo, que vinho eh?",
    "o rotulo ta meio apagado na foto, voces conseguem ler qual vinho eh?",
    "tirei print de um reels com uma garrafa, da pra identificar?",
    "esse vinho aqui da foto parece oxidado ou eh a cor normal?",
    "analisa essa foto aqui do fundo da garrafa, esse sedimento escuro eh normal?",
    "se eu te mandar a foto de uma garrafa sem rotulo voce consegue adivinhar?",
    "tirei foto desse rotulo mas o app nao reconhece, que vinho eh esse?",
    "foto do rotulo aqui, ta meio borrada, da pra identificar?",
    "encosta aqui uma foto desse espumante, quero saber se eh bom e onde comprar",
    "tenho uma foto de uma garrafa sem rotulo, so capsula dourada, da pra saber?",

    # R — GUARDA / CONSERVACAO (8)
    "vinho aberto dura quantos dias na geladeira?",
    "como armazenar vinho em apartamento sem adega?",
    "posso guardar vinho na geladeira por meses?",
    "vinho pode congelar? esqueci no freezer",
    "achei um vinho velho na garagem do meu avo, ainda da pra beber?",
    "como conservar vinho se morar num lugar quente?",
    "tem vinho que nao precisa ser guardado na adega?",
    "garrafa de 750ml vs magnum, a grande fica melhor com tempo?",

    # S — FORUM / COMUNIDADE (10)
    "comprei um vinho com rolha de plastico, isso eh sinal de baixa qualidade?",
    "no Vivino o pessoal fala bem desse Casal Garcia, mas ele eh doce ou so frutadinho?",
    "vi que esse vinho tem nota 4.2 no app, ele eh realmente tudo isso?",
    "por que o pessoal dos forums de vinho odeia tanto o Casillero del Diablo?",
    "comprei um Luigi Bosca Malbec e achei alcoolico demais, eh caracteristica ou garrafa ruim?",
    "por que tanta gente da 5 estrelas pra vinho super simples?",
    "esse hype todo com vinhos georgianos em qvevri faz sentido?",
    "vinho natural eh tao hypado e caro sendo que parece suco azedo, por que?",
    "unpopular opinion: vinhos do novo mundo sao melhores que do velho mundo. discuss",
    "comprei um Tannat e achei muito duro, eh normal?",

    # T — INFORMAL / WHATSAPP (8)
    "mano, preciso de um vinho bom pra levar hoje sem pagar mico, ate 60 reais",
    "irmao, to na loja aq, 50 conto, vinho bom pra hj a noite, manda logo",
    "foto do rotulo aq, eh bom isso? to na pressa",
    "eai, vinho tinto ou branco pra comemorar? nao entendo nada",
    "ce conhece aquele vinho da garrafa azul que vi no mercado? esqueci o nome kkk",
    "minha mina gosta de vinho doce, quero surpreender ela com algo melhor",
    "galera oq vcs tao bebendo hj? quero uma indicacao diferente",
    "Baco, me da uma dica de um vinho que ninguem conhece mas que seja sensacional",

    # U — TESTE DE LIMITES (11)
    "Baco existiu mesmo ou eh so mito?",
    "voce bebe vinho de verdade ou eh so um robo programado?",
    "qual o verdadeiro sentido da vida segundo a sabedoria de um sommelier digital?",
    "voce sabe me dizer o resultado do jogo do Flamengo?",
    "voce consegue fazer contas de matematica ou so entende de uva e terroir?",
    "posso dar vinho pro meu cachorro?",
    "qual vinho posso usar pra fazer limpeza da casa?",
    "cerveja eh melhor que vinho, muda minha opiniao",
    "qual melhor vinho pra tomar com Coca-Cola?",
    "pode misturar vinho tinto com refrigerante de limao ou isso eh pecado?",
    "meu tio falou de um vinho que tomou em 1998 na serra e so lembra que o rotulo era vermelho, tem como descobrir?",
]


def make_session_id():
    return str(uuid.uuid4())


def ask_baco(question: str, session_id: str) -> dict:
    """Envia uma pergunta ao Baco e retorna a resposta."""
    try:
        resp = requests.post(
            API_URL,
            json={"message": question, "session_id": session_id},
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        if resp.status_code == 429:
            return {"error": "rate_limited", "status": 429}
        if resp.status_code != 200:
            return {"error": resp.text, "status": resp.status_code}
        return resp.json()
    except requests.exceptions.Timeout:
        return {"error": "timeout", "status": 0}
    except Exception as e:
        return {"error": str(e), "status": 0}


def main():
    total = len(PERGUNTAS)
    print(f"=== Teste Baco: {total} perguntas ===\n")

    results = []
    session_id = make_session_id()
    session_count = 0
    errors = 0

    for i, pergunta in enumerate(PERGUNTAS, 1):
        # Rotacionar session_id a cada 5 perguntas (limite guest)
        if session_count >= GUEST_LIMIT:
            session_id = make_session_id()
            session_count = 0

        print(f"[{i}/{total}] {pergunta[:60]}...", end=" ", flush=True)

        resp = ask_baco(pergunta, session_id)
        session_count += 1

        if "error" in resp:
            # Se rate limited, tenta com nova sessao
            if resp.get("status") == 429:
                print("RATE LIMITED, nova sessao...", end=" ", flush=True)
                session_id = make_session_id()
                session_count = 0
                time.sleep(3)
                resp = ask_baco(pergunta, session_id)
                session_count += 1

        if "error" in resp:
            resposta = f"**ERRO:** {resp['error']}"
            errors += 1
            print(f"ERRO ({resp.get('status', '?')})")
        else:
            resposta = resp.get("response", "(sem resposta)")
            model = resp.get("model", "?")
            print(f"OK ({model})")

        results.append({
            "num": i,
            "pergunta": pergunta,
            "resposta": resposta,
            "model": resp.get("model", "?"),
        })

        time.sleep(DELAY_BETWEEN)

    # -----------------------------------------------------------------------
    # Gerar documento Markdown
    # -----------------------------------------------------------------------
    print(f"\n=== Gerando {OUTPUT_FILE} ===")

    lines = []
    lines.append("# Teste Baco — 246 Perguntas com Respostas\n")
    lines.append(f"> Gerado automaticamente em {time.strftime('%Y-%m-%d %H:%M')}\n")
    lines.append(f"> Total: {total} perguntas | Erros: {errors}\n")
    lines.append("---\n")

    # Categorias para headers
    categories = [
        (1, 35, "A — INICIANTE / CONHECIMENTO BASICO"),
        (36, 47, "B — ENTUSIASTA CASUAL"),
        (48, 62, "C — EXPERT / COLECIONADOR"),
        (63, 70, "D — PRESENTEADOR"),
        (71, 78, "E — PROFISSIONAL / RESTAURANTE"),
        (79, 86, "F — VIAJANTE"),
        (87, 98, "G — NO SUPERMERCADO"),
        (99, 108, "H — NO RESTAURANTE"),
        (109, 120, "I — CHURRASCO / JANTAR EM CASA"),
        (121, 135, "J — HARMONIZACAO ESPECIFICA"),
        (136, 143, "K — COMPRANDO ONLINE"),
        (144, 155, "L — REDES SOCIAIS / VIRAL"),
        (156, 167, "M — CUSTO-BENEFICIO"),
        (168, 179, "N — COMPARACOES"),
        (180, 189, "O — RANKINGS / LISTAS"),
        (190, 199, "P — ESTATISTICAS / DADOS"),
        (200, 209, "Q — FOTO / OCR"),
        (210, 217, "R — GUARDA / CONSERVACAO"),
        (218, 227, "S — FORUM / COMUNIDADE"),
        (228, 235, "T — INFORMAL / WHATSAPP"),
        (236, 246, "U — TESTE DE LIMITES"),
    ]

    cat_idx = 0
    for r in results:
        # Inserir header de categoria
        if cat_idx < len(categories):
            start, end, title = categories[cat_idx]
            if r["num"] == start:
                lines.append(f"\n## {title}\n")
            if r["num"] == end:
                cat_idx += 1

        lines.append(f"### {r['num']}. {r['pergunta']}\n")
        lines.append(f"{r['resposta']}\n")
        lines.append(f"*Modelo: {r['model']}*\n")
        lines.append("---\n")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nPronto! {total} perguntas processadas, {errors} erros.")
    print(f"Resultado em: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
