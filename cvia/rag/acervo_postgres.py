"""Acervo de artigos integros com Postgres (Supabase ou qualquer Postgres).
Mesma interface de AcervoArtigos (salvar/carregar/obter/total), pra poder
trocar um pelo outro via cvia.rag.fabrica_acervo sem alterar o resto do
pipeline.

Por que existe: em deploy serverless (Vercel/etc.) o disco nao e persistente
entre deploys/instancias, entao o acervo local (JSONL em dados/indice/) fica
vazio em producao. Guardando no mesmo Postgres do repositorio de trechos, o
artigo integro (texto + imagens) sobrevive ao deploy."""
from __future__ import annotations

import config
from ..ia.tipos import Artigo

TABELA = "cvia_artigos"


def _psycopg2():
    try:
        import psycopg2
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Pacote 'psycopg2-binary' nao instalado. Rode: pip install psycopg2-binary"
        ) from e
    return psycopg2


class AcervoPostgres:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or config.DATABASE_URL
        if not self.database_url:
            raise RuntimeError("Defina DATABASE_URL para usar o acervo postgres.")
        self._psycopg2 = _psycopg2()
        self._conn = self._psycopg2.connect(self.database_url)
        self._conn.autocommit = True
        self._garantir_schema()

    def _garantir_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(f"""
                create table if not exists {TABELA} (
                    artigo_id text primary key,
                    titulo text not null,
                    texto text not null,
                    url text not null,
                    categoria text not null default '',
                    pasta text not null default '',
                    atualizado_em text not null default ''
                );
            """)

    # --- escrita (ingestao) ---
    def salvar(self, artigos: list[Artigo]) -> None:
        from psycopg2.extras import execute_values
        linhas = [
            (a.artigo_id, a.titulo, a.texto, a.url, a.categoria, a.pasta, a.atualizado_em)
            for a in artigos
        ]
        with self._conn.cursor() as cur:
            cur.execute(f"truncate table {TABELA};")
            execute_values(
                cur,
                f"""insert into {TABELA}
                    (artigo_id, titulo, texto, url, categoria, pasta, atualizado_em)
                    values %s""",
                linhas,
            )

    # --- leitura (consulta) ---
    def carregar(self) -> "AcervoPostgres":
        return self

    def obter(self, artigo_id: str) -> dict | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""select artigo_id, titulo, texto, url, categoria, pasta, atualizado_em
                    from {TABELA} where artigo_id = %s;""",
                (str(artigo_id),),
            )
            row = cur.fetchone()
        if not row:
            return None
        campos = ["artigo_id", "titulo", "texto", "url", "categoria", "pasta", "atualizado_em"]
        return dict(zip(campos, row))

    @property
    def total(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute(f"select count(*) from {TABELA};")
            return cur.fetchone()[0]
