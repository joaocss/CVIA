"""Verificacao heuristica de fidelidade da resposta as fontes.

IMPORTANTE: isto NAO e deteccao real de alucinacao. E uma segunda chamada de
LLM (barata, max_tokens baixo) perguntando se a resposta se sustenta no
contexto recuperado. Serve para SINALIZAR casos para revisao humana no
painel — o resultado pode ele mesmo estar errado (o verificador tambem e uma
LLM). Trate `fiel=False` como "vale a pena olhar", nao como "esta errado"."""
from __future__ import annotations

import json

import config
from ..ia.tipos import ProvedorLlm

PROMPT_VERIFICACAO = (
    "Voce e um auditor de qualidade. Abaixo estao TRECHOS DE FONTE e uma "
    "RESPOSTA dada por outro assistente com base nesses trechos. Tres "
    "situacoes NAO sao falha de fidelidade — marque fiel=true nelas:\n\n"
    "1. A RESPOSTA recusa responder, diz que nao encontrou a informacao na "
    "base, pede para abrir atendimento, ou educadamente nega o pedido. Nao ha "
    "afirmacao factual pra verificar.\n"
    "2. A RESPOSTA reorganiza, resume ou junta num exemplo unico varios "
    "detalhes que aparecem em partes SEPARADAS dos TRECHOS DE FONTE — por "
    "exemplo, montar um corpo de requisicao juntando nomes de campo "
    "documentados em pontos diferentes do texto. Combinar informacao real "
    "que ja esta na fonte e sintese normal, nao invencao.\n"
    "3. A RESPOSTA menciona o nome do produto (CV CRM), recomenda abrir o "
    "artigo completo pra mais detalhes, ou lista os artigos usados. Isso e "
    "estrutura da resposta, nao uma afirmacao que precisa de fonte.\n\n"
    "Fora essas tres situacoes, verifique se as afirmacoes factuais da "
    "RESPOSTA (nomes de campo/header, passos, URLs, valores, metodo HTTP) "
    "estao sustentadas pelos TRECHOS DE FONTE. Marque fiel=false so quando a "
    "RESPOSTA afirma algo especifico e verificavel que os TRECHOS DE FONTE "
    "claramente nao contem ou contradizem — nao por causa de fraseado "
    "diferente ou por reunir informacao que esta espalhada na fonte. "
    "Preste atencao especial em URLs: cada bloco [Fonte N] do CONTEUDO DA "
    "BASE tem uma linha \"URL: ...\" — se a RESPOSTA citar um link que nao "
    "seja identico a uma dessas URLs, marque fiel=false com motivo "
    "\"URL nao corresponde a nenhuma fonte\".\n\n"
    "Responda APENAS com JSON estrito, sem texto ao redor: "
    '{{"fiel": true ou false, "motivo": "uma frase curta em portugues"}}\n\n'
    "### TRECHOS DE FONTE\n{contexto}\n\n### RESPOSTA A VERIFICAR\n{resposta}\n"
)


def verificar_fidelidade(
    resposta: str, contexto: str, llm: ProvedorLlm
) -> tuple[bool | None, str]:
    """Retorna (fiel, motivo). fiel=None quando a verificacao esta desligada
    ou falhou (nao decidir errado e melhor que decidir com base em erro)."""
    if not config.VERIFICAR_FIDELIDADE:
        return None, "verificacao desligada (CVIA_VERIFICAR_FIDELIDADE=false)"
    prompt = PROMPT_VERIFICACAO.format(contexto=contexto[:6000], resposta=resposta[:3000])
    try:
        saida = llm.gerar(prompt, max_tokens=150)
        texto = saida.texto.strip()
        inicio = texto.find("{")
        fim = texto.rfind("}")
        if inicio == -1 or fim == -1:
            return None, "resposta de verificacao nao veio em JSON"
        dados = json.loads(texto[inicio:fim + 1])
        return bool(dados.get("fiel", True)), str(dados.get("motivo", ""))[:300]
    except Exception as e:  # noqa
        return None, f"erro na verificacao: {e}"
