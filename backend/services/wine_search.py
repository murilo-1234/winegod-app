from db.queries import search_wines


def find_wines(query, limit=5):
    """Busca vinhos no banco por nome."""
    try:
        return search_wines(query, limit)
    except Exception:
        return []
