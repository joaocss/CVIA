"""API web do CVIA — expoe o mesmo pipeline do cvia.cli por HTTP, para deploy
online (Docker/Render/Railway/etc). Nao substitui o CLI, so adiciona uma
interface HTTP em cima dele.

Uso local:  uvicorn app:app --reload
Producao:   uvicorn app:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import sys
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
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from cvia.ia.fabrica_embeddings import criar_embeddings  # noqa: E402
from cvia.ia.fabrica_llm import criar_llm  # noqa: E402
from cvia.rag.assistente import Dependencias, responder  # noqa: E402
from cvia.rag.repositorio import RepositorioLocal  # noqa: E402

app = FastAPI(title="CVIA", description="Assistente RAG da base de conhecimento do CV CRM")

_origens = [o.strip() for o in os.getenv("CVIA_CORS_ORIGENS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origens,
    allow_methods=["*"],
    allow_headers=["*"],
)

_dep: Dependencias | None = None


def _dependencias() -> Dependencias:
    global _dep
    if _dep is None:
        repo = RepositorioLocal().carregar()
        _dep = Dependencias(embeddings=criar_embeddings(), llm=criar_llm(), repositorio=repo)
    return _dep


class PerguntaEntrada(BaseModel):
    pergunta: str
    historico: list[tuple[str, str]] | None = None


class FonteSaida(BaseModel):
    titulo: str
    url: str
    score: float


class RespostaSaida(BaseModel):
    resposta: str
    recusado: bool
    melhor_score: float
    modelo: str | None
    fontes: list[FonteSaida]


@app.get("/health")
def health() -> dict:
    repo = RepositorioLocal().carregar()
    return {
        "status": "ok" if repo.total > 0 else "indice_vazio",
        "indice_total": repo.total,
        "embedding_provedor": config.EMBEDDING_PROVEDOR,
        "llm_provedor": config.LLM_PROVEDOR,
    }


@app.post("/perguntar", response_model=RespostaSaida)
def perguntar(entrada: PerguntaEntrada) -> RespostaSaida:
    dep = _dependencias()
    if dep.repositorio.total == 0:
        raise HTTPException(503, "Indice vazio. Rode a extracao e ingestao antes de perguntar.")
    resultado = responder(entrada.pergunta, dep, entrada.historico)
    fontes = [
        FonteSaida(
            titulo=f.metadados.get("titulo", ""),
            url=f.metadados.get("url", ""),
            score=round(f.score, 3),
        )
        for f in (resultado.fontes if not resultado.recusado else [])
    ]
    return RespostaSaida(
        resposta=resultado.resposta,
        recusado=resultado.recusado,
        melhor_score=resultado.melhor_score,
        modelo=resultado.modelo,
        fontes=fontes,
    )


@app.get("/")
def pagina_inicial() -> dict:
    return {
        "servico": "CVIA",
        "docs": "/docs",
        "saude": "/health",
        "pergunta": "POST /perguntar {\"pergunta\": \"...\"}",
    }
