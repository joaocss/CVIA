"""Ingestao: para cada artigo -> chunk -> embedding (em lote) -> grava no
repositorio. Recebe os artigos ja extraidos e limpos (dataclass Artigo)."""
from __future__ import annotations

from ..ia.tipos import Artigo, ChunkParaInserir, ProvedorEmbeddings, RepositorioTrechos
from .chunker import chunkar


def ingerir(
    artigos: list[Artigo],
    embeddings: ProvedorEmbeddings,
    repositorio: RepositorioTrechos,
    tamanho_lote: int = 64,
) -> int:
    pendentes: list[tuple[Artigo, object]] = []
    for artigo in artigos:
        for trecho in chunkar(artigo.texto):
            pendentes.append((artigo, trecho))

    total = 0
    for inicio in range(0, len(pendentes), tamanho_lote):
        lote = pendentes[inicio:inicio + tamanho_lote]
        textos = [f"{a.titulo}\n{t.texto}" for a, t in lote]  # titulo ajuda o embedding
        vetores = embeddings.gerar_lote(textos)
        chunks: list[ChunkParaInserir] = []
        for (artigo, trecho), vetor in zip(lote, vetores):
            chunks.append(ChunkParaInserir(
                artigo_id=artigo.artigo_id,
                ordem=trecho.ordem,
                texto=trecho.texto,
                metadados={
                    "titulo": artigo.titulo,
                    "url": artigo.url,
                    "categoria": artigo.categoria,
                    "pasta": artigo.pasta,
                    "titulo_secao": trecho.titulo_secao,
                },
                embedding=vetor,
            ))
        repositorio.inserir(chunks)
        total += len(chunks)
    return total
