"""Pipeline do assistente de suporte do CV CRM:
  guardrail(entrada) -> minimiza PII -> embedding -> busca vetorial ->
  (grounding? senao "sem base") -> monta prompt -> LLM -> guardrail(saida).

Responde SOMENTE com base nos artigos da Base de Conhecimento. Quando nao ha
trecho suficientemente similar, avisa que nao encontrou e sugere abrir
atendimento — em vez de inventar (anti-alucinacao)."""
from __future__ import annotations

from dataclasses import dataclass, field

import config
from ..ia.tipos import ProvedorEmbeddings, ProvedorLlm, RepositorioTrechos, TrechoRecuperado
from .guardrails import (
    EventoGuardrail, MENSAGEM_SEM_BASE, guardrail_entrada, guardrail_saida, minimizar_pii,
)

REGRAS_SISTEMA = (
    "Voce e o assistente virtual de suporte do CV CRM (CRM do mercado imobiliario). "
    "Seu papel e responder duvidas de clientes e do time de suporte usando APENAS o "
    "CONTEUDO DA BASE de conhecimento fornecido abaixo. Responda em portugues, de forma "
    "objetiva e em passo a passo quando envolver configuracao. Use markdown (negrito nos "
    "termos-chave, listas numeradas). NAO invente funcionalidades, campos ou caminhos que "
    "nao estejam no material. Se o material nao cobrir a duvida, diga claramente que a "
    "informacao nao esta na base e sugira abrir atendimento com o suporte. Ao final, cite "
    "os artigos usados (titulo)."
)


@dataclass
class ResultadoAssistente:
    recusado: bool
    resposta: str
    fontes: list[TrechoRecuperado] = field(default_factory=list)
    eventos_entrada: list[EventoGuardrail] = field(default_factory=list)
    eventos_saida: list[EventoGuardrail] = field(default_factory=list)
    melhor_score: float = 0.0
    modelo: str | None = None


@dataclass
class Dependencias:
    embeddings: ProvedorEmbeddings
    llm: ProvedorLlm
    repositorio: RepositorioTrechos


def montar_contexto(fontes: list[TrechoRecuperado]) -> str:
    linhas = []
    for i, f in enumerate(fontes, 1):
        titulo = f.metadados.get("titulo", "")
        secao = f.metadados.get("titulo_secao", "")
        cabecalho = f"[Fonte {i}] {titulo}" + (f" — {secao}" if secao else "")
        linhas.append(f"{cabecalho}\n{f.texto}")
    return "\n\n".join(linhas)


def _montar_prompt(pergunta: str, contexto: str, historico: list[tuple[str, str]]) -> str:
    conversa = ""
    if historico:
        linhas = [f"{'Usuario' if a == 'usuario' else 'Assistente'}: {c}" for a, c in historico]
        conversa = "### CONVERSA ANTERIOR (contexto)\n" + "\n".join(linhas) + "\n\n"
    return (
        f"### REGRAS\n{REGRAS_SISTEMA}\n\n"
        f"### CONTEUDO DA BASE (fonte)\n{contexto}\n\n"
        f"{conversa}### PERGUNTA\n{pergunta}\n"
    )


def responder(
    pergunta: str,
    dep: Dependencias,
    historico: list[tuple[str, str]] | None = None,
) -> ResultadoAssistente:
    historico = historico or []
    eventos_entrada = guardrail_entrada(pergunta)
    pergunta_segura = minimizar_pii(pergunta)

    vetor = dep.embeddings.gerar(pergunta_segura)
    fontes = dep.repositorio.buscar(vetor, config.TOP_K)
    melhor = fontes[0].score if fontes else 0.0

    if not fontes or melhor < config.LIMIAR_GROUNDING:
        return ResultadoAssistente(
            recusado=True, resposta=MENSAGEM_SEM_BASE, fontes=fontes,
            eventos_entrada=eventos_entrada, melhor_score=round(melhor, 3),
        )

    contexto = montar_contexto(fontes)
    prompt = _montar_prompt(pergunta_segura, contexto, historico)
    saida = dep.llm.gerar(prompt, max_tokens=1200)
    texto, eventos_saida = guardrail_saida(saida.texto)

    return ResultadoAssistente(
        recusado=False, resposta=texto, fontes=fontes,
        eventos_entrada=eventos_entrada, eventos_saida=eventos_saida,
        melhor_score=round(melhor, 3), modelo=saida.modelo,
    )
