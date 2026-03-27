"""Tool de compartilhamento: share_results."""

import uuid


def share_results(wine_ids):
    """Gera link compartilhavel com vinhos selecionados."""
    share_id = str(uuid.uuid4())[:8]
    return {
        "share_id": share_id,
        "wine_ids": wine_ids,
        "message": (
            f"Link de compartilhamento gerado: ID {share_id}. "
            "Em breve este link sera acessivel via chat.winegod.ai/share/{share_id}"
        ),
    }
