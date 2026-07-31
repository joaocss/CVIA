"""Seleciona o repositorio de trechos (vector store). Controlado por
config.REPOSITORIO_PROVEDOR / env CVIA_REPOSITORIO (local | postgres)."""
from __future__ import annotations

import config


def criar_repositorio():
    if config.REPOSITORIO_PROVEDOR == "postgres":
        from .repositorio_postgres import RepositorioPostgres
        return RepositorioPostgres()
    from .repositorio import RepositorioLocal
    return RepositorioLocal()
