"""Log de interacoes para o painel de gestor (dashboard de uso/qualidade).

Independente do CVIA_REPOSITORIO (chunks podem estar local, os logs sempre
tentam ir para o Postgres se DATABASE_URL estiver configurado — sao poucas
linhas, nao precisa de pgvector). Se DATABASE_URL nao estiver configurado,
as funcoes de escrita viram no-op (best-effort: nunca deve quebrar a
resposta principal do assistente por falha de log).

Antes da autenticacao via API do Freshdesk existir, "usuario" e uma sessao
anonima gerada no navegador (guardada em localStorage) — usuario_id/
usuario_email ficam nulos ate a autenticacao real ser plugada aqui.
"""
from __future__ import annotations

import json
from dataclasses import asdict

import config

TABELA = "cvia_interacoes"


def _psycopg2():
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Pacote 'psycopg2-binary' nao instalado. Rode: pip install psycopg2-binary"
        ) from e
    return psycopg2


class RegistradorInteracoes:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or config.DATABASE_URL
        self.ativo = bool(self.database_url)
        self._conn = None
        if self.ativo:
            try:
                psycopg2 = _psycopg2()
                self._conn = psycopg2.connect(self.database_url)
                self._conn.autocommit = True
                self._garantir_schema()
            except Exception as e:  # noqa
                # nunca derruba o app por causa do log
                print(f"[interacoes] desativado (falha ao conectar): {e}")
                self.ativo = False
                self._conn = None

    def _garantir_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(f"""
                create table if not exists {TABELA} (
                    id bigserial primary key,
                    criado_em timestamptz not null default now(),
                    sessao_id text,
                    usuario_id text,
                    usuario_email text,
                    pergunta text not null,
                    resposta text not null,
                    recusado boolean not null default false,
                    melhor_score double precision,
                    modelo text,
                    guardrail_entrada jsonb not null default '[]'::jsonb,
                    guardrail_saida jsonb not null default '[]'::jsonb,
                    fontes jsonb not null default '[]'::jsonb,
                    fiel boolean,
                    fiel_motivo text,
                    duracao_ms integer
                );
            """)
            cur.execute(f"create index if not exists idx_{TABELA}_criado_em on {TABELA} (criado_em desc);")
            cur.execute(f"create index if not exists idx_{TABELA}_sessao on {TABELA} (sessao_id);")

    # --- escrita (best-effort, nunca propaga excecao) ---
    def registrar(
        self,
        *,
        sessao_id: str | None,
        pergunta: str,
        resposta: str,
        recusado: bool,
        melhor_score: float | None,
        modelo: str | None,
        guardrail_entrada: list,
        guardrail_saida: list,
        fontes: list,
        fiel: bool | None,
        fiel_motivo: str,
        duracao_ms: int,
        usuario_id: str | None = None,
        usuario_email: str | None = None,
    ) -> None:
        if not self.ativo:
            return
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    f"""insert into {TABELA}
                        (sessao_id, usuario_id, usuario_email, pergunta, resposta, recusado,
                         melhor_score, modelo, guardrail_entrada, guardrail_saida, fontes,
                         fiel, fiel_motivo, duracao_ms)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s)""",
                    (
                        sessao_id, usuario_id, usuario_email, pergunta, resposta, recusado,
                        melhor_score, modelo,
                        json.dumps([asdict(e) if not isinstance(e, dict) else e for e in guardrail_entrada], ensure_ascii=False),
                        json.dumps([asdict(e) if not isinstance(e, dict) else e for e in guardrail_saida], ensure_ascii=False),
                        json.dumps(fontes, ensure_ascii=False),
                        fiel, fiel_motivo, duracao_ms,
                    ),
                )
        except Exception as e:  # noqa
            print(f"[interacoes] falha ao registrar (ignorado): {e}")

    # --- leitura (para o painel) ---
    def resumo(self, dias: int = 30) -> dict:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""select
                        count(*) as total,
                        count(*) filter (where recusado) as recusadas,
                        avg(melhor_score) as score_medio,
                        count(*) filter (where jsonb_array_length(guardrail_entrada) > 0
                                            or jsonb_array_length(guardrail_saida) > 0) as com_guardrail,
                        count(*) filter (where fiel = false) as suspeita_alucinacao,
                        count(distinct sessao_id) as sessoes_unicas,
                        avg(duracao_ms) as duracao_media_ms
                    from {TABELA}
                    where criado_em > now() - interval '{int(dias)} days';"""
            )
            row = cur.fetchone()
        cols = ["total", "recusadas", "score_medio", "com_guardrail",
                "suspeita_alucinacao", "sessoes_unicas", "duracao_media_ms"]
        return dict(zip(cols, row))

    def serie_diaria(self, dias: int = 30) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""select date_trunc('day', criado_em)::date as dia,
                           count(*) as total,
                           count(*) filter (where recusado) as recusadas
                    from {TABELA}
                    where criado_em > now() - interval '{int(dias)} days'
                    group by 1 order by 1;"""
            )
            linhas = cur.fetchall()
        return [{"dia": str(d), "total": t, "recusadas": r} for d, t, r in linhas]

    def top_usuarios(self, limite: int = 10, dias: int = 30) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""select coalesce(usuario_email, sessao_id, 'desconhecido') as identificador,
                           (usuario_email is not null) as autenticado,
                           count(*) as total_perguntas,
                           max(criado_em) as ultima_pergunta
                    from {TABELA}
                    where criado_em > now() - interval '{int(dias)} days'
                    group by 1, 2
                    order by total_perguntas desc
                    limit %s;""",
                (limite,),
            )
            linhas = cur.fetchall()
        return [
            {"identificador": i, "autenticado": a, "total_perguntas": t, "ultima_pergunta": str(u)}
            for i, a, t, u in linhas
        ]

    def listar(
        self,
        limite: int = 50,
        offset: int = 0,
        so_recusadas: bool = False,
        so_guardrail: bool = False,
        so_suspeita: bool = False,
        busca: str | None = None,
    ) -> tuple[list[dict], int]:
        condicoes = ["1=1"]
        params: list = []
        if so_recusadas:
            condicoes.append("recusado = true")
        if so_guardrail:
            condicoes.append("(jsonb_array_length(guardrail_entrada) > 0 or jsonb_array_length(guardrail_saida) > 0)")
        if so_suspeita:
            condicoes.append("fiel = false")
        if busca:
            condicoes.append("(pergunta ilike %s or resposta ilike %s)")
            params.extend([f"%{busca}%", f"%{busca}%"])
        where = " and ".join(condicoes)

        with self._conn.cursor() as cur:
            cur.execute(f"select count(*) from {TABELA} where {where};", params)
            total = cur.fetchone()[0]
            cur.execute(
                f"""select id, criado_em, sessao_id, usuario_id, usuario_email, pergunta,
                           resposta, recusado, melhor_score, modelo, guardrail_entrada,
                           guardrail_saida, fontes, fiel, fiel_motivo, duracao_ms
                    from {TABELA}
                    where {where}
                    order by criado_em desc
                    limit %s offset %s;""",
                params + [limite, offset],
            )
            cols = [d[0] for d in cur.description]
            linhas = [dict(zip(cols, row)) for row in cur.fetchall()]
        for linha in linhas:
            linha["criado_em"] = str(linha["criado_em"])
        return linhas, total
