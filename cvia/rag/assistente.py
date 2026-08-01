"""Pipeline do assistente de suporte do CV CRM:
  guardrail(entrada) -> minimiza PII -> embedding -> busca vetorial ->
  (grounding? senao "sem base") -> monta prompt -> LLM -> guardrail(saida).

Responde SOMENTE com base nos artigos da Base de Conhecimento. Quando nao ha
trecho suficientemente similar, avisa que nao encontrou e sugere abrir
atendimento — em vez de inventar (anti-alucinacao)."""
from __future__ import annotations

from dataclasses import dataclass, field

import config
from ..ia.tipos import (
    ArtigoIntegral, ProvedorEmbeddings, ProvedorLlm, RepositorioTrechos, TrechoRecuperado,
)
from .acervo import AcervoArtigos
from .guardrails import (
    EventoGuardrail, MENSAGEM_SEM_BASE, guardrail_entrada, guardrail_saida, minimizar_pii,
)

# Quantos artigos integros no maximo reapresentar (e usar como contexto do LLM).
MAX_ARTIGOS_INTEGRAIS = 2
# Corte de caracteres por artigo ao montar o contexto do LLM (o artigo integro
# vai inteiro pra tela; aqui e so pra caber no prompt sem estourar token).
LIMITE_CONTEXTO_ARTIGO = 6000

REGRAS_SISTEMA = (
    "Voce e o assistente de suporte do CV CRM — o CRM do mercado imobiliario. Responda em "
    "portugues, usando so o CONTEUDO DA BASE abaixo; nao invente campo, endpoint, menu ou "
    "caminho que nao esteja documentado ali.\n\n"
    "IMPORTANTE sobre o formato da tela: logo abaixo da sua resposta, a interface exibe o "
    "ARTIGO COMPLETO da base, com o passo a passo e as imagens (prints das telas). Entao a "
    "sua parte NAO e repetir o artigo inteiro nem reescrever todos os passos — e um TEXTO "
    "COMPLEMENTAR, curto e didatico, que orienta a pessoa a executar o servico/tarefa/"
    "configuracao que ela pediu. Em 1 a 3 paragrafos curtos: confirme o que ela quer fazer, "
    "aponte o caminho principal e o pre-requisito que mais trava (permissao, cadastro previo, "
    "campo obrigatorio) e ja avise que o passo a passo completo com as telas esta logo abaixo. "
    "Se houver mais de um caminho (ex.: por lead ou reserva direta), diga em uma frase quando "
    "usar cada um. Nao numere de novo todos os passos do artigo.\n\n"
    "Escreva como alguem do time de suporte explicando pra um colega. Varie o tamanho das "
    "frases. Nao abra com \"claro!\" ou \"otima pergunta!\" e nao feche com torcida generica "
    "tipo \"espero ter ajudado\".\n\n"
    "Quando a base trouxer um endpoint de API, monte a requisicao (metodo HTTP, URL, "
    "cabecalhos, corpo de exemplo) usando SO o que estiver explicito no CONTEUDO DA BASE. Nao "
    "adivinhe metodo HTTP nem troque o esquema de autenticacao (ex.: nao escreva "
    "\"Authorization: Bearer\" se a base descreve headers separados de email e token). Se a "
    "base nao disser o metodo ou os headers exatos, diga isso em vez de completar com o que "
    "parece plausivel. Nos valores de exemplo use placeholders obviamente ficticios — token "
    "como SEU_TOKEN_AQUI, dominio como suaempresa.cvcrm.com.br — e deixe claro que a pessoa "
    "troca pelos dados reais antes de rodar.\n\n"
    "Se a base nao cobrir a duvida, diga isso com todas as letras e sugira abrir atendimento "
    "com o suporte — sem completar com uma resposta parecida."
)


@dataclass
class ResultadoAssistente:
    recusado: bool
    resposta: str
    fontes: list[TrechoRecuperado] = field(default_factory=list)
    artigos: list[ArtigoIntegral] = field(default_factory=list)
    eventos_entrada: list[EventoGuardrail] = field(default_factory=list)
    eventos_saida: list[EventoGuardrail] = field(default_factory=list)
    melhor_score: float = 0.0
    modelo: str | None = None


@dataclass
class Dependencias:
    embeddings: ProvedorEmbeddings
    llm: ProvedorLlm
    repositorio: RepositorioTrechos
    acervo: AcervoArtigos | None = None


def montar_contexto(fontes: list[TrechoRecuperado]) -> str:
    linhas = []
    for i, f in enumerate(fontes, 1):
        titulo = f.metadados.get("titulo", "")
        secao = f.metadados.get("titulo_secao", "")
        url = f.metadados.get("url", "")
        cabecalho = f"[Fonte {i}] {titulo}" + (f" — {secao}" if secao else "")
        linhas.append(f"{cabecalho}\nURL: {url}\n{f.texto}")
    return "\n\n".join(linhas)


def _artigo_id_do_chunk(f: TrechoRecuperado) -> str:
    # chunk_id = "artigo_id::ordem"
    return f.chunk_id.rsplit("::", 1)[0]


def resolver_artigos(
    fontes: list[TrechoRecuperado],
    acervo: AcervoArtigos | None,
    maximo: int = MAX_ARTIGOS_INTEGRAIS,
) -> list[ArtigoIntegral]:
    """Do(s) chunk(s) recuperado(s) para o(s) artigo(s) INTEGRO(S), sem repetir
    o mesmo artigo, preservando a ordem de relevancia."""
    if acervo is None:
        return []
    integrais: list[ArtigoIntegral] = []
    vistos: set[str] = set()
    for f in fontes:
        artigo_id = _artigo_id_do_chunk(f)
        if artigo_id in vistos:
            continue
        reg = acervo.obter(artigo_id)
        if not reg:
            continue
        vistos.add(artigo_id)
        integrais.append(ArtigoIntegral(
            artigo_id=artigo_id,
            titulo=reg.get("titulo", "") or f.metadados.get("titulo", ""),
            texto=reg.get("texto", ""),
            url=reg.get("url", "") or f.metadados.get("url", ""),
            categoria=reg.get("categoria", ""),
            pasta=reg.get("pasta", ""),
            score=round(f.score, 3),
        ))
        if len(integrais) >= maximo:
            break
    return integrais


def montar_contexto_integral(artigos: list[ArtigoIntegral]) -> str:
    linhas = []
    for i, a in enumerate(artigos, 1):
        corpo = a.texto[:LIMITE_CONTEXTO_ARTIGO]
        linhas.append(f"[Artigo {i}] {a.titulo}\nURL: {a.url}\n{corpo}")
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

    # Resolve o(s) artigo(s) INTEGRO(S) para reapresentacao e para dar ao LLM o
    # contexto completo (com o passo a passo), nao so o chunk recuperado.
    artigos = resolver_artigos(fontes, dep.acervo)
    contexto = montar_contexto_integral(artigos) if artigos else montar_contexto(fontes)
    prompt = _montar_prompt(pergunta_segura, contexto, historico)
    saida = dep.llm.gerar(prompt, max_tokens=1500)
    texto, eventos_saida = guardrail_saida(saida.texto)

    return ResultadoAssistente(
        recusado=False, resposta=texto, fontes=fontes, artigos=artigos,
        eventos_entrada=eventos_entrada, eventos_saida=eventos_saida,
        melhor_score=round(melhor, 3), modelo=saida.modelo,
    )
