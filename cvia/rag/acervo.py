"""Acervo de artigos integros: guarda o texto COMPLETO de cada artigo (em
markdown, com imagens inline) num JSONL, indexado por artigo_id.

Por que existe: o repositorio vetorial guarda CHUNKS — pedacos pequenos, bons
para achar o artigo certo por similaridade, mas ruins para apresentar. Na hora
de responder, o assistente usa o chunk so para localizar e depois resolve o
artigo_id no acervo para reapresentar o artigo NA INTEGRA (texto + prints),
como o CVrino faz. O acervo e gravado na ingestao e carregado na consulta.
"""
from __future__ import annotations

import json
from pathlib import Path

import config
from ..ia.tipos import Artigo


class AcervoArtigos:
    def __init__(self, arquivo: Path | None = None) -> None:
        self.arquivo = Path(arquivo or config.ARQUIVO_ACERVO)
        self._por_id: dict[str, dict] = {}

    # --- escrita (ingestao) ---
    def salvar(self, artigos: list[Artigo]) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        with self.arquivo.open("w", encoding="utf-8") as f:
            for a in artigos:
                registro = {
                    "artigo_id": a.artigo_id,
                    "titulo": a.titulo,
                    "texto": a.texto,
                    "url": a.url,
                    "categoria": a.categoria,
                    "pasta": a.pasta,
                    "atualizado_em": a.atualizado_em,
                }
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")

    # --- leitura (consulta) ---
    def carregar(self) -> "AcervoArtigos":
        self._por_id = {}
        if self.arquivo.exists():
            for linha in self.arquivo.read_text(encoding="utf-8").splitlines():
                if not linha.strip():
                    continue
                reg = json.loads(linha)
                self._por_id[str(reg.get("artigo_id"))] = reg
        return self

    def obter(self, artigo_id: str) -> dict | None:
        return self._por_id.get(str(artigo_id))

    @property
    def total(self) -> int:
        return len(self._por_id)
