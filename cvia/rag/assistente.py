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
    "Voce e o assistente de suporte do CV CRM — o CRM do mercado imobiliario. Responda em "
    "portugues, usando so o CONTEUDO DA BASE abaixo; nao invente campo, endpoint ou caminho "
    "que nao esteja documentado ali.\n\n"
    "Escreva como alguem do time de suporte explicando pra um colega, nao como uma lista "
    "telegrafica de topicos. Varie o tamanho das frases, use travessao pra encaixar uma "
    "explicacao no meio da frase quando fizer sentido, e evite paragrafos que so empilham "
    "gerundio pra parecer mais completos. Nao abra com \"claro!\" ou \"otima pergunta!\" e nao "
    "feche com frases de torcida generica tipo \"espero ter ajudado\".\n\n"
    "Quando a base trouxer um endpoint de API, monte a requisicao pro leitor (metodo HTTP, "
    "URL, cabecalhos, corpo de exemplo) usando SO o que estiver explicito no CONTEUDO DA "
    "BASE — metodo, nomes de header, nomes de campo. Nao adivinhe metodo HTTP nem troque o "
    "esquema de autenticacao (ex.: nao escreva \"Authorization: Bearer\" se a base descreve "
    "headers separados de email e token). Se a base nao disser o metodo ou os headers exatos, "
    "diga isso em vez de completar com o que parece plausivel. Nos valores de exemplo (nunca "
    "nos nomes de campo/header, que vem da base), use placeholders obviamente ficticios — "
    "token como SEU_TOKEN_AQUI, dominio como suaempresa.cvcrm.com.br — e deixe claro, na "
    "mesma frase, que a pessoa precisa trocar pelo e-mail, token e dominio reais da conta "
    "dela antes de rodar.\n\n"
    "Ao citar um artigo, nao deixe o link solto no fim do texto. No meio da explicacao, diga "
    "que vale abrir o artigo completo pra ver o passo a passo com telas ou mais detalhes, e "
    "coloque o link ali mesmo.\n\n"
    "Se a base nao cobrir a duvida, diga isso com todas as letras e sugira abrir atendimento "
    "com o suporte — sem tentar completar com uma resposta parecida. No fim, liste os artigos "
    "usados (titulo e link)."
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
    saida = dep.llm.gerar(prompt, max_tokens=1500)
    texto, eventos_saida = guardrail_saida(saida.texto)

    return ResultadoAssistente(
        recusado=False, resposta=texto, fontes=fontes,
        eventos_entrada=eventos_entrada, eventos_saida=eventos_saida,
        melhor_score=round(melhor, 3), modelo=saida.modelo,
    )
