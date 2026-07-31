"""Interface de linha de comando do CVIA.

Comandos:
  extrair            Baixa a Base de Conhecimento do CV CRM -> dados/artigos.jsonl
  ingerir [arquivo]  Chunk + embeddings dos artigos -> indice vetorial
  perguntar "..."    Faz uma pergunta ao assistente (one-shot)
  chat               Conversa interativa com o assistente
  info               Mostra provedores e tamanho do indice

Exemplos:
  python -m cvia.cli extrair
  python -m cvia.cli ingerir dados/artigos_amostra.jsonl
  CVIA_EMBEDDING_PROVEDOR=local python -m cvia.cli perguntar "Como criar um webhook?"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Console do Windows por padrao nao usa UTF-8 (cp1252), o que derruba o
# processo com UnicodeEncodeError ao imprimir titulos com emoji/acentos
# (mesmo com stdout redirecionado para arquivo). Forca UTF-8 com
# substituicao em vez de erro.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _carregar_env() -> None:
    """Le um .env simples da raiz do projeto para os.environ (sem dependencia).
    Executado ANTES de importar `config`, para que as variaveis do .env sejam
    vistas quando o config avalia os parametros de modulo (provedor, modelos)."""
    arq = Path(__file__).resolve().parent.parent / ".env"
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env()

import config
from .ia.fabrica_embeddings import criar_embeddings
from .ia.fabrica_llm import criar_llm
from .ia.tipos import Artigo
from .rag.assistente import Dependencias, responder
from .rag.ingestao import ingerir
from .rag.fabrica_repositorio import criar_repositorio


def carregar_artigos(arquivo: Path) -> list[Artigo]:
    artigos: list[Artigo] = []
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        d = json.loads(linha)
        artigos.append(Artigo(**d))
    return artigos


def cmd_extrair(args) -> None:
    from .extracao import extrator_local
    from .extracao.extrator_desenvolvedor import ExtratorDesenvolvedor
    from .extracao.extrator_freshdesk import ExtratorFreshdesk
    saida = Path(args.saida) if args.saida else config.ARQUIVO_ARTIGOS

    total = 0
    if not args.sem_ajuda:
        total += ExtratorFreshdesk().extrair_tudo(saida=saida, modo="w")
    if not args.sem_dev:
        modo = "a" if not args.sem_ajuda else "w"
        total += ExtratorDesenvolvedor().extrair_tudo(saida=saida, modo=modo)
    if not args.sem_local:
        modo = "a" if (not args.sem_ajuda or not args.sem_dev) else "w"
        total += extrator_local.extrair_tudo(saida=saida, modo=modo)
    print(f"\nTotal geral: {total} documentos -> {saida}")


def cmd_ingerir(args) -> None:
    arquivo = Path(args.arquivo) if args.arquivo else config.ARQUIVO_ARTIGOS
    if not arquivo.exists():
        sys.exit(f"Arquivo nao encontrado: {arquivo}. Rode 'extrair' antes ou aponte a amostra.")
    artigos = carregar_artigos(arquivo)
    embeddings = criar_embeddings()
    repo = criar_repositorio()
    repo.limpar()
    total = ingerir(artigos, embeddings, repo)
    repo.salvar()
    destino = getattr(repo, "dir_indice", None) or f"postgres ({config.REPOSITORIO_PROVEDOR})"
    print(f"Ingeridos {total} trechos de {len(artigos)} artigos "
          f"(embeddings={embeddings.nome}) -> {destino}")


def _dependencias() -> Dependencias:
    repo = criar_repositorio().carregar()
    if repo.total == 0:
        sys.exit("Indice vazio. Rode 'python -m cvia.cli ingerir' antes.")
    return Dependencias(embeddings=criar_embeddings(), llm=criar_llm(), repositorio=repo)


def _mostrar(resultado) -> None:
    print("\n" + resultado.resposta + "\n")
    if resultado.fontes and not resultado.recusado:
        print("Fontes:")
        vistos = set()
        for f in resultado.fontes:
            titulo = f.metadados.get("titulo", "")
            url = f.metadados.get("url", "")
            chave = (titulo, url)
            if chave in vistos:
                continue
            vistos.add(chave)
            print(f"  - {titulo} ({url}) [score={f.score:.3f}]")
    print(f"\n[melhor_score={resultado.melhor_score} | modelo={resultado.modelo}]")


def cmd_perguntar(args) -> None:
    dep = _dependencias()
    _mostrar(responder(args.pergunta, dep))


def cmd_chat(args) -> None:
    dep = _dependencias()
    historico: list[tuple[str, str]] = []
    print("CVIA — assistente de suporte do CV CRM. Ctrl+C para sair.\n")
    try:
        while True:
            pergunta = input("Voce: ").strip()
            if not pergunta:
                continue
            r = responder(pergunta, dep, historico)
            _mostrar(r)
            historico.append(("usuario", pergunta))
            historico.append(("assistente", r.resposta))
            historico = historico[-6:]  # janela curta de contexto
    except (KeyboardInterrupt, EOFError):
        print("\nAte mais!")


def cmd_info(args) -> None:
    repo = criar_repositorio().carregar()
    destino = getattr(repo, "dir_indice", None) or f"postgres ({config.REPOSITORIO_PROVEDOR})"
    print(f"Embedding: {config.EMBEDDING_PROVEDOR} | LLM: {config.LLM_PROVEDOR}")
    print(f"Repositorio: {config.REPOSITORIO_PROVEDOR}")
    print(f"Indice: {repo.total} trechos em {destino}")
    print(f"Limiar de grounding: {config.LIMIAR_GROUNDING} | TOP_K: {config.TOP_K}")


def principal(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="cvia", description="Assistente RAG da base de ajuda do CV CRM")
    sub = p.add_subparsers(dest="comando", required=True)

    pe = sub.add_parser("extrair", help="baixa a base de conhecimento")
    pe.add_argument("--saida", help="arquivo jsonl de saida")
    pe.add_argument("--sem-ajuda", action="store_true", help="pula ajuda.cvcrm.com.br")
    pe.add_argument("--sem-dev", action="store_true", help="pula desenvolvedor.cvcrm.com.br")
    pe.add_argument("--sem-local", action="store_true", help="pula documentos locais (extradoc)")
    pe.set_defaults(func=cmd_extrair)

    pi = sub.add_parser("ingerir", help="gera o indice vetorial")
    pi.add_argument("arquivo", nargs="?", help="jsonl de artigos (padrao: dados/artigos.jsonl)")
    pi.set_defaults(func=cmd_ingerir)

    pp = sub.add_parser("perguntar", help="pergunta unica")
    pp.add_argument("pergunta")
    pp.set_defaults(func=cmd_perguntar)

    pc = sub.add_parser("chat", help="conversa interativa")
    pc.set_defaults(func=cmd_chat)

    pinfo = sub.add_parser("info", help="status do indice e provedores")
    pinfo.set_defaults(func=cmd_info)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    principal()
