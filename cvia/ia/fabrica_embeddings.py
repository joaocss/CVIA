"""Seleciona o provedor de embeddings (o MESMO deve ser usado na ingestao e na
consulta). Controlado por config.EMBEDDING_PROVEDOR / env CVIA_EMBEDDING_PROVEDOR."""
from __future__ import annotations

import config
from .tipos import ProvedorEmbeddings


def criar_embeddings() -> ProvedorEmbeddings:
    provedor = config.EMBEDDING_PROVEDOR
    if provedor == "openai":
        from .provedor_openai import EmbeddingsOpenAI
        return EmbeddingsOpenAI()
    if provedor == "local":
        from .provedor_local import EmbeddingsLocal
        return EmbeddingsLocal()
    from .provedor_mock import EmbeddingsMock
    return EmbeddingsMock(config.DIMENSAO_MOCK)
