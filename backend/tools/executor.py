"""Executor central: recebe tool_name + args e executa a funcao certa."""

import json
from tools.search import search_wine, get_similar_wines
from tools.details import get_wine_details, get_wine_history
from tools.prices import get_prices, get_store_wines
from tools.compare import compare_wines, get_recommendations
from tools.media import process_image, process_video, process_pdf, process_voice
from tools.location import get_nearby_stores
from tools.share import share_results
from tools.stats import get_wine_stats

# Mapa de tools disponiveis
TOOL_MAP = {
    "search_wine": search_wine,
    "get_wine_details": get_wine_details,
    "get_prices": get_prices,
    "compare_wines": compare_wines,
    "get_recommendations": get_recommendations,
    "process_image": process_image,
    "process_video": process_video,
    "process_pdf": process_pdf,
    "process_voice": process_voice,
    "get_store_wines": get_store_wines,
    "get_similar_wines": get_similar_wines,
    "get_wine_history": get_wine_history,
    "get_nearby_stores": get_nearby_stores,
    "share_results": share_results,
    "get_wine_stats": get_wine_stats,
}


def execute_tool(tool_name, tool_input):
    """Executa uma tool pelo nome e retorna o resultado como string JSON."""
    func = TOOL_MAP.get(tool_name)
    if not func:
        return json.dumps({"error": f"Tool '{tool_name}' nao encontrada."})

    try:
        result = func(**tool_input)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": f"Erro ao executar '{tool_name}': {str(e)}"})
