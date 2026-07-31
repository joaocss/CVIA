"""Repositorio de trechos: vector store local, sem banco externo. Guarda os
vetores numa matriz numpy e os metadados num JSONL. Busca por similaridade de
cosseno (vetores sao normalizados na ingestao/consulta -> produto interno).

Escolha deliberada da versao "simplificada em Python": zero dependencia de
Supabase/pgvector, roda em qualquer maquina. Para escalar a base inteira, este
modulo pode ser trocado por FAISS/Chroma sem alterar o restante do pipeline
(a interface RepositorioTrechos e a mesma)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import config
from ..ia.tipos import ChunkParaInserir, TrechoRecuperado


class RepositorioLocal:
    def __init__(self, dir_indice: Path | None = None) -> None:
        self.dir_indice = Path(dir_indice or config.DIR_INDICE)
        self.dir_indice.mkdir(parents=True, exist_ok=True)
        self.arq_vetores = self.dir_indice / "vetores.npy"
        self.arq_meta = self.dir_indice / "chunks.jsonl"
        self._matriz: np.ndarray | None = None
        self._meta: list[dict] = []

    # --- escrita ---
    def inserir(self, chunks: list[ChunkParaInserir]) -> None:
        for c in chunks:
            self._meta.append({
                "chunk_id": f"{c.artigo_id}::{c.ordem}",
                "artigo_id": c.artigo_id,
                "ordem": c.ordem,
                "texto": c.texto,
                "metadados": c.metadados,
            })
        novos = np.array([c.embedding for c in chunks], dtype=np.float32)
        if self._matriz is None or self._matriz.size == 0:
            self._matriz = novos
        else:
            self._matriz = np.vstack([self._matriz, novos])

    def salvar(self) -> None:
        if self._matriz is None:
            self._matriz = np.zeros((0, 0), dtype=np.float32)
        np.save(self.arq_vetores, self._matriz)
        with self.arq_meta.open("w", encoding="utf-8") as f:
            for m in self._meta:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")

    # --- leitura ---
    def carregar(self) -> "RepositorioLocal":
        if self.arq_vetores.exists():
            self._matriz = np.load(self.arq_vetores)
        if self.arq_meta.exists():
            self._meta = [json.loads(l) for l in self.arq_meta.read_text(encoding="utf-8").splitlines() if l.strip()]
        return self

    def limpar(self) -> None:
        self._matriz = None
        self._meta = []

    @property
    def total(self) -> int:
        return len(self._meta)

    def buscar(self, consulta: list[float], limite: int) -> list[TrechoRecuperado]:
        if self._matriz is None or self._matriz.size == 0:
            return []
        q = np.asarray(consulta, dtype=np.float32)
        nq = np.linalg.norm(q)
        if nq > 0:
            q = q / nq
        # matriz ja normalizada na ingestao; normalizamos por seguranca
        normas = np.linalg.norm(self._matriz, axis=1, keepdims=True)
        normas[normas == 0] = 1.0
        base = self._matriz / normas
        scores = base @ q
        ordem = np.argsort(-scores)[:limite]
        resultados: list[TrechoRecuperado] = []
        for i in ordem:
            m = self._meta[int(i)]
            resultados.append(TrechoRecuperado(
                chunk_id=m["chunk_id"],
                texto=m["texto"],
                metadados=m["metadados"],
                score=float(scores[int(i)]),
            ))
        return resultados
