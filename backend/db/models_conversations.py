import json
import psycopg2
from db.connection import get_connection, release_connection


class DuplicateConversationError(Exception):
    """Levantada quando ja existe conversa com o mesmo id."""
    pass


def create_conversation(conversation_id, user_id, title=None, messages=None):
    """Cria uma conversa nova. Retorna o dict da conversa criada.
    Levanta DuplicateConversationError se o id ja existir."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conversations (id, user_id, title, messages)
                VALUES (%s, %s, %s, %s::jsonb)
                RETURNING id, user_id, title, messages,
                          created_at, updated_at, is_saved, saved_at
            """, (
                conversation_id,
                user_id,
                title,
                json.dumps(messages or []),
            ))
            row = cur.fetchone()
            conn.commit()
            return _row_to_dict(row)
    except psycopg2.IntegrityError:
        conn.rollback()
        raise DuplicateConversationError(conversation_id)
    finally:
        release_connection(conn)


def get_conversation(conversation_id):
    """Retorna conversa por ID ou None."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, title, messages,
                       created_at, updated_at, is_saved, saved_at
                FROM conversations WHERE id = %s
            """, (conversation_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None
    finally:
        release_connection(conn)


def list_conversations(user_id, query=None, saved=None, limit=50, offset=0):
    """Lista conversas de um usuario, ordenadas por updated_at DESC.
    Se query for fornecido, filtra por title (ILIKE).
    Se saved for True/False, filtra por is_saved."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            conditions = ["user_id = %s"]
            params = [user_id]

            if query:
                conditions.append("title ILIKE %s")
                params.append(f"%{query}%")

            if saved is not None:
                conditions.append("is_saved = %s")
                params.append(saved)

            order_by = (
                "saved_at DESC NULLS LAST, updated_at DESC"
                if saved
                else "updated_at DESC"
            )

            cur.execute(f"""
                SELECT id, user_id, title, '[]'::jsonb AS messages,
                       created_at, updated_at, is_saved, saved_at
                FROM conversations
                WHERE {' AND '.join(conditions)}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            rows = cur.fetchall()
            return [_row_to_dict(r) for r in rows]
    finally:
        release_connection(conn)


def update_conversation(conversation_id, title=None, messages=None):
    """Atualiza title e/ou messages de uma conversa. Retorna dict atualizado ou None."""
    sets = []
    params = []
    if title is not None:
        sets.append("title = %s")
        params.append(title)
    if messages is not None:
        sets.append("messages = %s::jsonb")
        params.append(json.dumps(messages))
    if not sets:
        return get_conversation(conversation_id)

    sets.append("updated_at = NOW()")
    params.append(conversation_id)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE conversations
                SET {', '.join(sets)}
                WHERE id = %s
                RETURNING id, user_id, title, messages,
                          created_at, updated_at, is_saved, saved_at
            """, params)
            row = cur.fetchone()
            conn.commit()
            return _row_to_dict(row) if row else None
    finally:
        release_connection(conn)


def delete_conversation(conversation_id):
    """Deleta conversa. Retorna True se existia, False se nao."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM conversations WHERE id = %s", (conversation_id,)
            )
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
    finally:
        release_connection(conn)


def set_saved(conversation_id, saved):
    """Marca ou desmarca conversa como salva. Retorna dict atualizado ou None."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if saved:
                cur.execute("""
                    UPDATE conversations
                    SET is_saved = TRUE, saved_at = NOW()
                    WHERE id = %s
                    RETURNING id, user_id, title, messages,
                              created_at, updated_at, is_saved, saved_at
                """, (conversation_id,))
            else:
                cur.execute("""
                    UPDATE conversations
                    SET is_saved = FALSE, saved_at = NULL
                    WHERE id = %s
                    RETURNING id, user_id, title, messages,
                              created_at, updated_at, is_saved, saved_at
                """, (conversation_id,))
            row = cur.fetchone()
            conn.commit()
            return _row_to_dict(row) if row else None
    finally:
        release_connection(conn)


def _row_to_dict(row):
    """Converte row do cursor para dict padrao."""
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "title": row[2],
        "messages": row[3] if isinstance(row[3], list) else [],
        "created_at": str(row[4]) if row[4] else None,
        "updated_at": str(row[5]) if row[5] else None,
        "is_saved": row[6],
        "saved_at": str(row[7]) if row[7] else None,
    }
