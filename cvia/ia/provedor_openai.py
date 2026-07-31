"""Provedores OpenAI (opcionais). Requerem OPENAI_API_KEY e o pacote openai.
Import preguicoso: so quebra se o provedor for realmente selecionado."""
from __future__ import annotations

import os

import config
from .tipos import RespostaLlm


def _cliente():
    try:
        from openai import OpenAI
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Pacote 'openai' nao instalado. Rode: pip install openai"
        ) from e
    chave = os.getenv("OPENAI_API_KEY")
    if not chave:
        raise RuntimeError("Defina OPENAI_API_KEY para usar o provedor OpenAI.")
    return OpenAI(api_key=chave)


class EmbeddingsOpenAI:
    def __init__(self, modelo: str | None = None) -> None:
        self.modelo = modelo or config.MODELO_EMBEDDING_OPENAI
        self.nome = f"openai:{self.modelo}"
        # text-embedding-3-small = 1536; small com dimensions reduz. Mantemos padrao.
        self.dimensao = 1536

    def gerar(self, texto: str) -> list[float]:
        return self.gerar_lote([texto])[0]

    def gerar_lote(self, textos: list[str]) -> list[list[float]]:
        cliente = _cliente()
        resp = cliente.embeddings.create(model=self.modelo, input=textos)
        return [d.embedding for d in resp.data]


class LlmOpenAI:
    def __init__(self, modelo: str | None = None) -> None:
        self.modelo = modelo or config.MODELO_LLM_OPENAI
        self.nome = f"openai:{self.modelo}"

    def gerar(self, prompt: str, max_tokens: int = 1200) -> RespostaLlm:
        cliente = _cliente()
        resp = cliente.chat.completions.create(
            model=self.modelo,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        uso = resp.usage
        return RespostaLlm(
            texto=resp.choices[0].message.content or "",
            modelo=self.modelo,
            tokens_entrada=getattr(uso, "prompt_tokens", None),
            tokens_saida=getattr(uso, "completion_tokens", None),
        )
