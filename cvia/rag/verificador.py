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
    "RESPOSTA dada por outro assistente com base nesses trechos.\n\n"
    "Primeiro cheque: a RESPOSTA recusa responder, diz que nao encontrou a "
    "informacao na base, pede para abrir atendimento, ou educadamente nega o "
    "pedido (ex.: pergunta fora do escopo, pedido de piada, etc.)? Se sim, "
    "isso NAO e uma falha de fidelidade — nao ha afirmacao factual para "
    "verificar, marque fiel=true.\n\n"
    "Caso contrario, verifique se as afirmacoes factuais da RESPOSTA (nomes "
    "de campos, passos, URLs, valores) estao sustentadas pelos TRECHOS DE "
    "FONTE. Nao precisa ser copia literal, mas o conteudo tem que estar la "
    "ou ser inferencia direta — marque fiel=false so quando a RESPOSTA "
    "afirma algo especifico que os TRECHOS DE FONTE nao sustentam.\n\n"
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
