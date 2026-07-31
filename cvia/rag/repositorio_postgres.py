"""Repositorio de trechos com Postgres + pgvector (Supabase ou qualquer
Postgres com a extensao vector habilitada). Mesma interface de
RepositorioLocal (inserir/buscar/carregar/salvar/limpar/total), pra poder
trocar um pelo outro via cvia.rag.fabrica_repositorio sem alterar o resto
do pipeline.

So faz sentido com embeddings de dimensao fixa (aqui, 1536 — text-embedding-
3-small da OpenAI). Trocar de provedor de embeddings exige recriar a tabela.
"""
from __future__ import annotations

import json

import config
from ..ia.tipos import ChunkParaInserir, TrechoRecuperado

DIMENSAO = 1536
TABELA = "cvia_chunks"


def _psycopg2():
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Pacote 'psycopg2-binary' nao instalado. Rode: pip install psycopg2-binary"
        ) from e
    return psycopg2


def _vetor_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in v) + "]"


class RepositorioPostgres:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or config.DATABASE_URL
        if not self.database_url:
            raise RuntimeError("Defina DATABASE_URL para usar o repositorio postgres.")
        self._psycopg2 = _psycopg2()
        self._conn = self._psycopg2.connect(self.database_url)
        self._conn.autocommit = True
        self._garantir_schema()

    def _garantir_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("create extension if not exists vector;")
            cur.execute(f"""
                create table if not exists {TABELA} (
                    chunk_id text primary key,
                    artigo_id text not null,
                    ordem integer not null,
                    texto text not null,
                    metadados jsonb not null default '{{}}'::jsonb,
                    embedding vector({DIMENSAO}) not null
                );
            """)
            cur.execute(f"""
                create index if not exists idx_{TABELA}_embedding
                on {TABELA} using hnsw (embedding vector_cosine_ops);
            """)

    # --- escrita ---
    def limpar(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(f"truncate table {TABELA};")

    def inserir(self, chunks: list[ChunkParaInserir]) -> None:
        from psycopg2.extras import execute_values
        linhas = [
            (
                f"{c.artigo_id}::{c.ordem}",
                c.artigo_id,
                c.ordem,
                c.texto,
                json.dumps(c.metadados, ensure_ascii=False),
                _vetor_literal(c.embedding),
            )
            for c in chunks
        ]
        with self._conn.cursor() as cur:
            execute_values(
                cur,
                f"""insert into {TABELA} (chunk_id, artigo_id, ordem, texto, metadados, embedding)
                    values %s
                    on conflict (chunk_id) do update set
                        texto = excluded.texto,
                        metadados = excluded.metadados,
                        embedding = excluded.embedding""",
                linhas,
                template="(%s, %s, %s, %s, %s::jsonb, %s::vector)",
            )

    def salvar(self) -> None:
        pass  # cada inserir() ja commita (autocommit=True)

    # --- leitura ---
    def carregar(self) -> "RepositorioPostgres":
        return self

    @property
    def total(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute(f"select count(*) from {TABELA};")
            return cur.fetchone()[0]

    def buscar(self, consulta: list[float], limite: int) -> list[TrechoRecuperado]:
        vetor = _vetor_literal(consulta)
        with self._conn.cursor() as cur:
            cur.execute(
                f"""select chunk_id, texto, metadados, 1 - (embedding <=> %s::vector) as score
                    from {TABELA}
                    order by embedding <=> %s::vector
                    limit %s;""",
                (vetor, vetor, limite),
            )
            linhas = cur.fetchall()
        return [
            TrechoRecuperado(chunk_id=row[0], texto=row[1], metadados=row[2], score=float(row[3]))
            for row in linhas
        ]
