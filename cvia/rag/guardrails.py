"""Guardrails do assistente de suporte. Foco: privacidade (LGPD) e robustez.
Entrada: mascara PII (email, telefone, CPF), sinaliza tentativa de injection.
Saida: nao deixa vazar PII na resposta."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..ia.texto import normalizar

TEM_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
TEM_TELEFONE = re.compile(r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?9?\d{4}[-\s]?\d{4}\b")
TEM_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")

PADRAO_INJECTION = [
    "ignore as instrucoes", "esqueca as regras", "aja como", "desconsidere",
    "voce agora e", "ignore o contexto",
]


@dataclass
class EventoGuardrail:
    categoria: str   # pii | injection
    acao: str        # reescrito | alerta
    severidade: str  # baixa | media | alta
    detalhe: str


def guardrail_entrada(pergunta: str) -> list[EventoGuardrail]:
    eventos: list[EventoGuardrail] = []
    if TEM_EMAIL.search(pergunta) or TEM_TELEFONE.search(pergunta) or TEM_CPF.search(pergunta):
        eventos.append(EventoGuardrail("pii", "reescrito", "media",
                                       "dado pessoal removido antes do envio ao modelo"))
    p = normalizar(pergunta)
    if any(t in p for t in PADRAO_INJECTION):
        eventos.append(EventoGuardrail("injection", "alerta", "media",
                                       "possivel tentativa de burlar as regras"))
    return eventos


def minimizar_pii(texto: str) -> str:
    texto = TEM_EMAIL.sub("[email]", texto)
    texto = TEM_CPF.sub("[cpf]", texto)
    texto = TEM_TELEFONE.sub("[telefone]", texto)
    return texto


def guardrail_saida(resposta: str) -> tuple[str, list[EventoGuardrail]]:
    eventos: list[EventoGuardrail] = []
    texto = resposta
    if TEM_EMAIL.search(resposta) or TEM_TELEFONE.search(resposta) or TEM_CPF.search(resposta):
        texto = minimizar_pii(resposta)
        eventos.append(EventoGuardrail("pii", "reescrito", "media",
                                       "dado pessoal removido da resposta"))
    return texto, eventos


MENSAGEM_SEM_BASE = (
    "Nao encontrei um artigo na Base de Conhecimento do CV CRM que responda a essa "
    "duvida com seguranca. Vale refinar a pergunta ou abrir um atendimento com o "
    "suporte tecnico pelo chat do Painel do Gestor."
)
