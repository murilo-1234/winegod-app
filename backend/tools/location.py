"""Tool de localizacao: get_nearby_stores."""


def get_nearby_stores(latitude, longitude, radius_km=50):
    """STUB — geolocalizacao das lojas nao existe ainda."""
    return {
        "message": (
            "A busca por lojas proximas ainda esta sendo implementada. "
            "Em breve voce podera encontrar lojas perto de voce! "
            "Por enquanto, me diga sua cidade que eu tento ajudar."
        ),
        "status": "not_implemented",
        "coordinates_received": {"lat": latitude, "lng": longitude},
    }
