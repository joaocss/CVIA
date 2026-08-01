"""Contratos (interfaces) da camada de IA. Trocar de provedor = trocar a
implementacao, sem tocar no pipeline do assistente. Espelha a arquitetura do
projeto de referencia (SaaS_Escolar_IA), portada de TypeScript para Python."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProvedorEmbeddings(Protocol):
    nome: str
    dimensao: int

    def gerar(self, texto: str) -> list[float]:
        """Vetor de um unico texto."""
        ...

    def gerar_lote(self, textos: list[str]) -> list[list[float]]:
        """Vetor de varios textos numa chamada (evita rate limit na ingestao)."""
        ...


@dataclass
class RespostaLlm:
    texto: str
    modelo: str
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


@runtime_checkable
class ProvedorLlm(Protocol):
    nome: str

    def gerar(self, prompt: str, max_tokens: int = 1200) -> RespostaLlm:
        ...


@dataclass
class ChunkParaInserir:
    artigo_id: str
    ordem: int
    texto: str
    metadados: dict[str, Any]
    embedding: list[float]


@dataclass
class TrechoRecuperado:
    chunk_id: str
    texto: str
    metadados: dict[str, Any]
    score: float


@dataclass
class ArtigoIntegral:
    """Artigo completo (markdown com imagens inline) resolvido a partir do
    chunk recuperado, para reapresentacao na integra na resposta."""
    artigo_id: str
    titulo: str
    texto: str
    url: str
    categoria: str = ""
    pasta: str = ""
    score: float = 0.0


@runtime_checkable
class RepositorioTrechos(Protocol):
    def inserir(self, chunks: list[ChunkParaInserir]) -> None:
        ...

    def buscar(self, consulta: list[float], limite: int) -> list[TrechoRecuperado]:
        ...


@dataclass
class Artigo:
    """Um artigo da base de conhecimento, ja extraido e limpo."""
    artigo_id: str
    titulo: str
    texto: str
    url: str
    categoria: str = ""
    pasta: str = ""
    atualizado_em: str = ""
    metadados: dict[str, Any] = field(default_factory=dict)
