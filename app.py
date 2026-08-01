"""API web do CVIA — expoe o mesmo pipeline do cvia.cli por HTTP, para deploy
online (Docker/Render/Railway/Vercel/etc), mais um painel de gestor (uso,
qualidade, guardrails) em /admin. Nao substitui o CLI, so adiciona uma
interface HTTP em cima dele.

Uso local:  uvicorn app:app --reload
Producao:   uvicorn app:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import sys
import time
from dataclasses import asdict
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# mesmo truque do cli.py: carregar .env antes de importar config, para que
# provedores/limiar sejam lidos corretamente.
import os  # noqa: E402


def _carregar_env() -> None:
    arq = Path(__file__).resolve().parent / ".env"
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env()

import config  # noqa: E402
from fastapi import FastAPI, Header, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from cvia.ia.fabrica_embeddings import criar_embeddings  # noqa: E402
from cvia.ia.fabrica_llm import criar_llm  # noqa: E402
from cvia.rag.assistente import Dependencias, montar_contexto, responder  # noqa: E402
from cvia.rag.fabrica_acervo import criar_acervo  # noqa: E402
from cvia.rag.fabrica_repositorio import criar_repositorio  # noqa: E402
from cvia.rag.interacoes import RegistradorInteracoes  # noqa: E402
from cvia.rag.verificador import verificar_fidelidade  # noqa: E402

app = FastAPI(title="CVIA", description="Assistente RAG da base de conhecimento do CV CRM")

_origens = [o.strip() for o in os.getenv("CVIA_CORS_ORIGENS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origens,
    allow_methods=["*"],
    allow_headers=["*"],
)

_dep: Dependencias | None = None
_registrador: RegistradorInteracoes | None = None


def _dependencias() -> Dependencias:
    global _dep
    if _dep is None:
        repo = criar_repositorio().carregar()
        acervo = criar_acervo().carregar()
        _dep = Dependencias(
            embeddings=criar_embeddings(), llm=criar_llm(), repositorio=repo, acervo=acervo,
        )
    return _dep


def _log() -> RegistradorInteracoes:
    global _registrador
    if _registrador is None:
        _registrador = RegistradorInteracoes()
    return _registrador


def _exigir_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not config.ADMIN_TOKEN:
        raise HTTPException(403, "Painel admin desabilitado (CVIA_ADMIN_TOKEN nao configurado).")
    if not x_admin_token or x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(401, "Token invalido.")


class PerguntaEntrada(BaseModel):
    pergunta: str
    historico: list[tuple[str, str]] | None = None
    sessao_id: str | None = None


class FonteSaida(BaseModel):
    titulo: str
    url: str
    score: float


class ArtigoSaida(BaseModel):
    titulo: str
    url: str
    texto: str
    categoria: str = ""
    pasta: str = ""
    score: float = 0.0


class RespostaSaida(BaseModel):
    resposta: str
    recusado: bool
    melhor_score: float
    modelo: str | None
    fontes: list[FonteSaida]
    artigos: list[ArtigoSaida] = []


class RetomarSaida(BaseModel):
    tem_historico: bool
    ultima_pergunta: str | None = None
    quando: str | None = None
    historico: list[tuple[str, str]] = []


@app.get("/health")
def health() -> dict:
    repo = criar_repositorio().carregar()
    return {
        "status": "ok" if repo.total > 0 else "indice_vazio",
        "indice_total": repo.total,
        "embedding_provedor": config.EMBEDDING_PROVEDOR,
        "llm_provedor": config.LLM_PROVEDOR,
        "logs_ativos": _log().ativo,
    }


@app.post("/perguntar", response_model=RespostaSaida)
def perguntar(entrada: PerguntaEntrada) -> RespostaSaida:
    dep = _dependencias()
    if dep.repositorio.total == 0:
        raise HTTPException(503, "Indice vazio. Rode a extracao e ingestao antes de perguntar.")

    inicio = time.perf_counter()
    resultado = responder(entrada.pergunta, dep, entrada.historico)
    duracao_ms = int((time.perf_counter() - inicio) * 1000)

    fiel: bool | None = None
    fiel_motivo = ""
    if not resultado.recusado:
        contexto = montar_contexto(resultado.fontes)
        fiel, fiel_motivo = verificar_fidelidade(resultado.resposta, contexto, dep.llm)

    fontes_saida = [
        FonteSaida(
            titulo=f.metadados.get("titulo", ""),
            url=f.metadados.get("url", ""),
            score=round(f.score, 3),
        )
        for f in (resultado.fontes if not resultado.recusado else [])
    ]

    try:
        _log().registrar(
            sessao_id=entrada.sessao_id,
            pergunta=entrada.pergunta,
            resposta=resultado.resposta,
            recusado=resultado.recusado,
            melhor_score=resultado.melhor_score,
            modelo=resultado.modelo,
            guardrail_entrada=[asdict(e) for e in resultado.eventos_entrada],
            guardrail_saida=[asdict(e) for e in resultado.eventos_saida],
            fontes=[f.model_dump() for f in fontes_saida],
            fiel=fiel,
            fiel_motivo=fiel_motivo,
            duracao_ms=duracao_ms,
        )
    except Exception as e:  # noqa — log nunca pode derrubar a resposta
        print(f"[perguntar] falha ao registrar interacao (ignorado): {e}")

    artigos_saida = [
        ArtigoSaida(
            titulo=a.titulo,
            url=a.url,
            texto=a.texto,
            categoria=a.categoria,
            pasta=a.pasta,
            score=round(a.score, 3),
        )
        for a in (resultado.artigos if not resultado.recusado else [])
    ]

    return RespostaSaida(
        resposta=resultado.resposta,
        recusado=resultado.recusado,
        melhor_score=resultado.melhor_score,
        modelo=resultado.modelo,
        fontes=fontes_saida,
        artigos=artigos_saida,
    )


@app.get("/sessao/retomar", response_model=RetomarSaida)
def sessao_retomar(sessao_id: str = Query(...)) -> RetomarSaida:
    """Consultado ao abrir o chat: se a mesma sessao (futuramente o mesmo
    usuario autenticado pelo Freshdesk) tiver conversa recente registrada,
    devolve o suficiente pra UI perguntar se a pessoa quer continuar de onde
    parou. Best-effort: se o log estiver desativado, so diz que nao ha
    historico em vez de quebrar a abertura do chat."""
    reg = _log()
    if not reg.ativo:
        return RetomarSaida(tem_historico=False)
    conversa = reg.ultima_conversa(sessao_id=sessao_id)
    if not conversa:
        return RetomarSaida(tem_historico=False)
    return RetomarSaida(
        tem_historico=True,
        ultima_pergunta=conversa["ultima_pergunta"],
        quando=conversa["quando"],
        historico=[tuple(par) for par in conversa["historico"]],
    )


# --- Painel de gestor (admin) ------------------------------------------------

@app.get("/admin/api/resumo")
def admin_resumo(dias: int = Query(30, ge=1, le=365), x_admin_token: str | None = Header(default=None)) -> dict:
    _exigir_admin(x_admin_token)
    reg = _log()
    if not reg.ativo:
        raise HTTPException(503, "Log de interacoes desativado (DATABASE_URL nao configurado).")
    return reg.resumo(dias=dias)


@app.get("/admin/api/serie-diaria")
def admin_serie_diaria(dias: int = Query(30, ge=1, le=365), x_admin_token: str | None = Header(default=None)) -> list[dict]:
    _exigir_admin(x_admin_token)
    reg = _log()
    if not reg.ativo:
        raise HTTPException(503, "Log de interacoes desativado.")
    return reg.serie_diaria(dias=dias)


@app.get("/admin/api/usuarios")
def admin_usuarios(
    dias: int = Query(30, ge=1, le=365),
    limite: int = Query(10, ge=1, le=100),
    x_admin_token: str | None = Header(default=None),
) -> list[dict]:
    _exigir_admin(x_admin_token)
    reg = _log()
    if not reg.ativo:
        raise HTTPException(503, "Log de interacoes desativado.")
    return reg.top_usuarios(limite=limite, dias=dias)


@app.get("/admin/api/interacoes")
def admin_interacoes(
    limite: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    so_recusadas: bool = Query(False),
    so_guardrail: bool = Query(False),
    so_suspeita: bool = Query(False),
    busca: str | None = Query(None),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    _exigir_admin(x_admin_token)
    reg = _log()
    if not reg.ativo:
        raise HTTPException(503, "Log de interacoes desativado.")
    linhas, total = reg.listar(
        limite=limite, offset=offset,
        so_recusadas=so_recusadas, so_guardrail=so_guardrail, so_suspeita=so_suspeita,
        busca=busca,
    )
    return {"total": total, "itens": linhas}


_DIR_STATIC = Path(__file__).resolve().parent / "static"


@app.get("/")
def pagina_inicial() -> FileResponse:
    return FileResponse(_DIR_STATIC / "index.html")


@app.get("/admin")
def pagina_admin() -> FileResponse:
    return FileResponse(_DIR_STATIC / "admin.html")


@app.get("/api")
def info_api() -> dict:
    return {
        "servico": "CVIA",
        "docs": "/docs",
        "saude": "/health",
        "pergunta": "POST /perguntar {\"pergunta\": \"...\"}",
        "admin": "/admin (requer token)",
    }


if _DIR_STATIC.exists():
    app.mount("/static", StaticFiles(directory=_DIR_STATIC), name="static")
