"""Tools de detalhes: get_wine_details, get_wine_history."""

from db.connection import get_connection, release_connection


def get_wine_details(wine_id):
    """Retorna todos os dados de um vinho especifico."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM wines WHERE id = %s", (wine_id,))
            row = cur.fetchone()
            if not row:
                return {"error": "Vinho nao encontrado"}
            columns = [desc[0] for desc in cur.description]
            result = dict(zip(columns, row))

            # Converter Decimal/tipos especiais para JSON-safe
            for k, v in result.items():
                if hasattr(v, 'as_integer_ratio'):
                    result[k] = float(v)
                elif hasattr(v, 'isoformat'):
                    result[k] = v.isoformat()

            return result
    finally:
        release_connection(conn)


def get_wine_history(wine_id):
    """STUB — historico de preco nao existe ainda. Retorna preco atual."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, preco_min, preco_max, moeda FROM wines WHERE id = %s",
                (wine_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"error": "Vinho nao encontrado"}
            columns = [desc[0] for desc in cur.description]
            result = dict(zip(columns, row))
            for k, v in result.items():
                if hasattr(v, 'as_integer_ratio'):
                    result[k] = float(v)
            result["message"] = (
                "Historico de precos ainda nao disponivel. "
                "Mostrando preco atual."
            )
            return result
    finally:
        release_connection(conn)
