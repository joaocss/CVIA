"""Carrega documentos locais (markdown) como artigos da base de conhecimento.

Usa uma lista explicita em vez de varrer a pasta inteira: alguns arquivos em
extradoc/ sao anotacoes de chamados com dados de cliente (nomes, e-mails) e
nao devem ser vetorizados como estao; versoes com esses dados removidos
ficam em extradoc_limpo/. Arquivos binarios (.skill, .svg) e scripts de
teste (.py) tambem ficam de fora.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import config
from ..ia.tipos import Artigo

RAIZ_EXTRACAO = Path(__file__).resolve().parent

ARQUIVOS_LOCAIS: list[tuple[str, str]] = [
    ("extradoc/trecho_skill_erp-sienge_baseDateInterest.md", "Integracao Sienge"),
    ("extradoc/origemcv_leads.md", "API de Leads"),
    ("extradoc_limpo/clicksign_edicao_manual_signatario.md", "Integracao Clicksign"),
]


def _titulo(texto: str, arquivo: Path) -> str:
    for linha in texto.splitlines():
        linha = linha.strip()
        if linha.startswith("#"):
            return linha.lstrip("#").strip()
    return arquivo.stem


def extrair_tudo(saida: Path | None = None, verbose: bool = True, modo: str = "a") -> int:
    saida = Path(saida or config.ARQUIVO_ARTIGOS)
    saida.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with saida.open(modo, encoding="utf-8") as f:
        for rel, categoria in ARQUIVOS_LOCAIS:
            caminho = RAIZ_EXTRACAO / rel
            if not caminho.exists():
                if verbose:
                    print(f"  ! nao encontrado: {caminho}")
                continue
            texto = caminho.read_text(encoding="utf-8").strip()
            if len(texto) < 40:
                continue
            artigo = Artigo(
                artigo_id=caminho.stem,
                titulo=_titulo(texto, caminho),
                texto=texto,
                url=f"local://{rel}",
                categoria=categoria,
                pasta="Documentacao Interna",
                atualizado_em="",
                metadados={},
            )
            f.write(json.dumps(asdict(artigo), ensure_ascii=False) + "\n")
            total += 1
            if verbose:
                print(f"  + [local] {artigo.titulo[:70]}")
    if verbose:
        print(f"[local] Total carregado: {total} documentos -> {saida}")
    return total
