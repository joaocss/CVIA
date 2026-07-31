"""Provedores mock: rodam offline, sem chave de API. Servem para testar o
pipeline (ingestao + busca + resposta) de ponta a ponta.

O embedding mock NAO e aleatorio: usa "hashing bag-of-words" (cada token cai
numa posicao do vetor por hash). Assim, sobreposicao de palavras entre a
pergunta e o trecho gera similaridade real — o suficiente para validar a
recuperacao sem depender de um modelo semantico."""
from __future__ import annotations

import hashlib
import math

from .texto import tokenizar


def _hash_posicao(token: str, dimensao: int) -> int:
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(h, 16) % dimensao


class EmbeddingsMock:
    def __init__(self, dimensao: int = 512) -> None:
        self.nome = f"mock-hashing-{dimensao}"
        self.dimensao = dimensao

    def gerar(self, texto: str) -> list[float]:
        vetor = [0.0] * self.dimensao
        for token in tokenizar(texto):
            pos = _hash_posicao(token, self.dimensao)
            # sinal deterministico por token evita cancelamento sistematico
            sinal = 1.0 if _hash_posicao(token + "#s", 2) == 0 else -1.0
            vetor[pos] += sinal
        norma = math.sqrt(sum(v * v for v in vetor))
        if norma > 0:
            vetor = [v / norma for v in vetor]
        return vetor

    def gerar_lote(self, textos: list[str]) -> list[list[float]]:
        return [self.gerar(t) for t in textos]


class LlmMock:
    def __init__(self) -> None:
        self.nome = "mock-llm"

    def gerar(self, prompt: str, max_tokens: int = 1200):
        from .tipos import RespostaLlm

        # Extrai o bloco de contexto do prompt para deixar claro, no teste, que
        # a resposta esta ancorada nas fontes recuperadas.
        marca = "### CONTEUDO DA BASE (fonte)"
        contexto = ""
        if marca in prompt:
            contexto = prompt.split(marca, 1)[1].split("###", 1)[0].strip()
        resumo = (contexto[:600] + "...") if len(contexto) > 600 else contexto
        texto = (
            "[RESPOSTA MOCK — sem LLM real]\n\n"
            "Com base nos artigos da base de conhecimento do CV CRM:\n\n"
            f"{resumo or '(nenhum trecho de contexto foi fornecido)'}"
        )
        return RespostaLlm(texto=texto, modelo=self.nome, tokens_entrada=0, tokens_saida=0)
