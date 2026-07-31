"""Quebra o texto de um artigo em trechos (chunks). Estrategia: respeitar as
secoes marcadas por titulo markdown (##) e, dentro delas, agrupar paragrafos
ate um tamanho-alvo com sobreposicao. Limpa ruido comum do portal Freshdesk
(bloco de feedback, navegacao, chamadas de marketing)."""
from __future__ import annotations

import re
from dataclasses import dataclass

import config

# Trechos de ruido que sobram mesmo apos a limpeza de HTML.
RUIDOS = [
    re.compile(r"este artigo foi util.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"sua gestao comercial pode ir alem.*?clicando aqui!?", re.IGNORECASE),
    re.compile(r"boas vendas!?", re.IGNORECASE),
]


@dataclass
class Trecho:
    ordem: int
    titulo_secao: str
    texto: str


def limpar_ruido(texto: str) -> str:
    t = texto
    for r in RUIDOS:
        t = r.sub(" ", t)
    # remove linhas de imagem markdown e urls soltas de imagem
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def _dividir_por_tamanho(texto: str, alvo: int, sobreposicao: int) -> list[str]:
    paragrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if len(p.strip()) > 2]
    blocos: list[str] = []
    buffer = ""
    for par in paragrafos:
        if buffer and len(buffer) + len(par) + 1 > alvo:
            blocos.append(buffer.strip())
            cauda = buffer[-sobreposicao:] if sobreposicao else ""
            buffer = f"{cauda} {par}".strip()
        else:
            buffer = f"{buffer} {par}".strip() if buffer else par
    if buffer.strip():
        blocos.append(buffer.strip())
    return blocos


def chunkar(
    texto: str,
    tamanho_alvo: int | None = None,
    sobreposicao: int | None = None,
) -> list[Trecho]:
    alvo = tamanho_alvo or config.CHUNK_TAMANHO_ALVO
    sobre = sobreposicao if sobreposicao is not None else config.CHUNK_SOBREPOSICAO
    limpo = limpar_ruido(texto)

    # Quebra por secao (## Titulo). O texto antes do primeiro ## vira "Introducao".
    partes = re.split(r"\n#{2,3}\s+", "\n" + limpo)
    secoes: list[tuple[str, str]] = []
    for i, parte in enumerate(partes):
        if not parte.strip():
            continue
        if i == 0:
            secoes.append(("", parte.strip()))
        else:
            linhas = parte.split("\n", 1)
            titulo = linhas[0].strip().strip("*# ")
            corpo = linhas[1].strip() if len(linhas) > 1 else ""
            secoes.append((titulo, corpo))

    trechos: list[Trecho] = []
    ordem = 0
    for titulo, corpo in secoes:
        base = f"{titulo}\n\n{corpo}" if titulo else corpo
        for bloco in _dividir_por_tamanho(base, alvo, sobre):
            if len(bloco.strip()) < 20:
                continue
            trechos.append(Trecho(ordem=ordem, titulo_secao=titulo, texto=bloco.strip()))
            ordem += 1
    return trechos
