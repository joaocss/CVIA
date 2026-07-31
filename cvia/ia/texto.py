"""Utilitarios de normalizacao de texto (usados por guardrails e pelo
embedding mock)."""
from __future__ import annotations

import re
import unicodedata


def remover_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minusculas, sem acento, espacos colapsados. Base estavel para regex."""
    return re.sub(r"\s+", " ", remover_acentos(texto).lower()).strip()


def tokenizar(texto: str) -> list[str]:
    """Tokens alfanumericos simples (para o embedding mock por hashing)."""
    return re.findall(r"[a-z0-9]{2,}", normalizar(texto))
