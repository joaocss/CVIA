"""Seleciona o acervo de artigos integros. Controlado por
config.REPOSITORIO_PROVEDOR / env CVIA_REPOSITORIO (local | postgres) — o
mesmo interruptor usado pelo repositorio de trechos, para os dois ficarem
sempre no mesmo lugar (senao o artigo integro some em deploy serverless)."""
from __future__ import annotations

import config


def criar_acervo():
    if config.REPOSITORIO_PROVEDOR == "postgres":
        from .acervo_postgres import AcervoPostgres
        return AcervoPostgres()
    from .acervo import AcervoArtigos
    return AcervoArtigos()
