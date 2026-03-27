"""JSON schemas das 14 tools para Claude API."""

TOOLS = [
    {
        "name": "search_wine",
        "description": (
            "Busca vinhos por nome, produtor ou regiao usando busca fuzzy. "
            "Use quando o usuario mencionar um vinho especifico, produtor, ou quiser encontrar vinhos por nome."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nome do vinho, produtor, ou regiao para buscar",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximo de resultados (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_wine_details",
        "description": (
            "Retorna todos os detalhes de um vinho especifico pelo ID. "
            "Use apos uma busca quando precisar de informacoes completas sobre um vinho."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wine_id": {
                    "type": "integer",
                    "description": "ID do vinho no banco de dados",
                },
            },
            "required": ["wine_id"],
        },
    },
    {
        "name": "get_prices",
        "description": (
            "Retorna precos de um vinho nas lojas disponiveis. "
            "Use quando o usuario perguntar preco, onde comprar, ou quiser comparar precos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wine_id": {
                    "type": "integer",
                    "description": "ID do vinho",
                },
                "country": {
                    "type": "string",
                    "description": "Filtrar por pais da loja (opcional)",
                },
            },
            "required": ["wine_id"],
        },
    },
    {
        "name": "compare_wines",
        "description": (
            "Compara 2 a 5 vinhos lado a lado. "
            "Use quando o usuario pedir para comparar vinhos especificos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wine_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Lista de IDs dos vinhos para comparar (2 a 5)",
                    "minItems": 2,
                    "maxItems": 5,
                },
            },
            "required": ["wine_ids"],
        },
    },
    {
        "name": "get_recommendations",
        "description": (
            "Recomenda vinhos com base em filtros como tipo, pais, regiao, uva, faixa de preco. "
            "Use quando o usuario pedir recomendacoes, sugestoes, ou 'me indica um vinho'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "description": "Tipo do vinho: tinto, branco, rose, espumante, sobremesa, fortificado",
                },
                "pais": {
                    "type": "string",
                    "description": "Pais de origem (ex: Argentina, France, Italy)",
                },
                "regiao": {
                    "type": "string",
                    "description": "Regiao vinicola (ex: Mendoza, Bordeaux, Toscana)",
                },
                "uva": {
                    "type": "string",
                    "description": "Uva/casta principal (ex: Malbec, Cabernet Sauvignon)",
                },
                "preco_min": {
                    "type": "number",
                    "description": "Preco minimo",
                },
                "preco_max": {
                    "type": "number",
                    "description": "Preco maximo",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximo de resultados (default 5)",
                    "default": 5,
                },
            },
            "required": [],
        },
    },
    {
        "name": "process_image",
        "description": (
            "Processa imagem de rotulo de vinho ou cardapio usando OCR. "
            "Use quando o usuario enviar uma foto de rotulo, cardapio ou garrafa."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "base64_image": {
                    "type": "string",
                    "description": "Imagem codificada em base64",
                },
            },
            "required": ["base64_image"],
        },
    },
    {
        "name": "process_video",
        "description": (
            "Processa video de rotulo de vinho. "
            "Use quando o usuario enviar um video."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "base64_video": {
                    "type": "string",
                    "description": "Video codificado em base64",
                },
            },
            "required": ["base64_video"],
        },
    },
    {
        "name": "process_pdf",
        "description": (
            "Processa PDF de carta de vinhos ou catalogo. "
            "Use quando o usuario enviar um arquivo PDF."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "base64_pdf": {
                    "type": "string",
                    "description": "PDF codificado em base64",
                },
            },
            "required": ["base64_pdf"],
        },
    },
    {
        "name": "process_voice",
        "description": (
            "Processa texto transcrito de audio do usuario. "
            "Use quando o usuario enviar mensagem de voz (texto ja transcrito pelo frontend)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "audio_text": {
                    "type": "string",
                    "description": "Texto transcrito do audio do usuario",
                },
            },
            "required": ["audio_text"],
        },
    },
    {
        "name": "get_store_wines",
        "description": (
            "Busca vinhos disponiveis em uma loja especifica. "
            "Use quando o usuario perguntar sobre vinhos de uma loja."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "store_name": {
                    "type": "string",
                    "description": "Nome da loja (busca parcial)",
                },
                "tipo": {
                    "type": "string",
                    "description": "Filtrar por tipo de vinho (opcional)",
                },
                "preco_max": {
                    "type": "number",
                    "description": "Preco maximo (opcional)",
                },
            },
            "required": ["store_name"],
        },
    },
    {
        "name": "get_similar_wines",
        "description": (
            "Encontra vinhos similares a um vinho especifico (mesma uva, regiao, faixa de preco). "
            "Use quando o usuario pedir alternativas, similares, ou 'algo parecido'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wine_id": {
                    "type": "integer",
                    "description": "ID do vinho de referencia",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximo de resultados (default 5)",
                    "default": 5,
                },
            },
            "required": ["wine_id"],
        },
    },
    {
        "name": "get_wine_history",
        "description": (
            "Retorna historico de precos de um vinho. "
            "Use quando o usuario perguntar se o preco subiu, desceu, ou historico."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wine_id": {
                    "type": "integer",
                    "description": "ID do vinho",
                },
            },
            "required": ["wine_id"],
        },
    },
    {
        "name": "get_nearby_stores",
        "description": (
            "Encontra lojas de vinho proximas a uma localizacao. "
            "Use quando o usuario perguntar sobre lojas perto dele."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "number",
                    "description": "Latitude do usuario",
                },
                "longitude": {
                    "type": "number",
                    "description": "Longitude do usuario",
                },
                "radius_km": {
                    "type": "number",
                    "description": "Raio de busca em km (default 50)",
                    "default": 50,
                },
            },
            "required": ["latitude", "longitude"],
        },
    },
    {
        "name": "share_results",
        "description": (
            "Gera link compartilhavel com vinhos selecionados. "
            "Use quando o usuario quiser compartilhar ou salvar resultados."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wine_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Lista de IDs dos vinhos para compartilhar",
                },
            },
            "required": ["wine_ids"],
        },
    },
]
