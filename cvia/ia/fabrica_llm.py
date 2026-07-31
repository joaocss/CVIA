"""Seleciona o provedor de geracao (LLM). Controlado por config.LLM_PROVEDOR /
env CVIA_LLM_PROVEDOR."""
from __future__ import annotations

import config
from .tipos import ProvedorLlm


def criar_llm() -> ProvedorLlm:
    if config.LLM_PROVEDOR == "openai":
        from .provedor_openai import LlmOpenAI
        return LlmOpenAI()
    from .provedor_mock import LlmMock
    return LlmMock()
