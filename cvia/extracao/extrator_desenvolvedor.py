"""Crawler do Portal do Desenvolvedor do CV CRM (ReadMe.io).

O site e uma SPA React, mas cada pagina e servida com o conteudo ja
embutido em `<script id="ssr-props">` (JSON usado para hidratar a pagina).
Isso evita precisar de um browser: um GET simples + parse do JSON basta.

Fluxo:
  1. Baixa o sitemap.xml e classifica cada URL por prefixo (docs, page,
     reference, changelog).
  2. Para paginas de doc/page: extrai o corpo em markdown de
     `document.content.body`.
  3. Para paginas de referencia de API (endpoint): localiza a operacao
     correspondente (metodo+path) dentro do schema OpenAPI embutido e monta
     um texto com titulo, endpoint, parametros e a descricao (que no CV
     costuma ser a documentacao funcional completa do endpoint).
  4. Changelog e ignorado por padrao (notas de release tem baixo valor para
     perguntas de suporte).

Uso:  python -m cvia.cli extrair
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from urllib.parse import unquote

import config
from ..ia.tipos import Artigo

RE_SSR_PROPS = re.compile(r'<script id="ssr-props"[^>]*>(.*?)</script>', re.S)
RE_LOC = re.compile(r"<loc>(.*?)</loc>")


def _requests():
    try:
        import requests
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Pacote 'requests' nao instalado. Rode: pip install requests") from e
    return requests


def _tipo_da_url(url: str) -> str | None:
    if "/docs/" in url:
        return "docs"
    if "/reference/" in url:
        return "reference"
    if "/page/" in url:
        return "page"
    if "/changelog" in url:
        return "changelog"
    if url.rstrip("/").endswith(".com.br"):
        return None  # home
    return None


def _categoria_de_uri(uri: str | None, padrao: str) -> str:
    if not uri:
        return padrao
    ultimo = uri.rstrip("/").rsplit("/", 1)[-1]
    return unquote(ultimo).replace("-", " ").strip() or padrao


class ExtratorDesenvolvedor:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or config.BASE_URL_DEV).rstrip("/")
        requests = _requests()
        self.sessao = requests.Session()
        self.sessao.headers.update({"User-Agent": config.EXTRACAO_USER_AGENT})

    def _baixar(self, url: str) -> str:
        ultimo = None
        for tentativa in range(config.EXTRACAO_TENTATIVAS):
            try:
                resp = self.sessao.get(url, timeout=30)
                resp.raise_for_status()
                time.sleep(config.EXTRACAO_INTERVALO_S)
                return resp.text
            except Exception as e:  # noqa
                ultimo = e
                time.sleep(1.5 * (tentativa + 1))
        raise RuntimeError(f"Falha ao baixar {url}: {ultimo}")

    def urls_do_sitemap(self, incluir_changelog: bool = False) -> list[tuple[str, str]]:
        xml = self._baixar(f"{self.base_url}/sitemap.xml")
        pares: list[tuple[str, str]] = []
        for url in RE_LOC.findall(xml):
            tipo = _tipo_da_url(url)
            if tipo is None:
                continue
            if tipo == "changelog" and not incluir_changelog:
                continue
            pares.append((url, tipo))
        return pares

    def _ssr_document(self, html: str) -> dict | None:
        m = RE_SSR_PROPS.search(html)
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("document")

    def _operacao_do_endpoint(self, doc: dict) -> dict | None:
        api = doc.get("api") or {}
        schema = api.get("schema") or {}
        paths = schema.get("paths") or {}
        metodo = (api.get("method") or "").lower()
        caminho = api.get("path") or ""
        ops = paths.get(caminho)
        if ops and metodo in ops:
            return ops[metodo]
        for p, metodos in paths.items():
            if p.rstrip("/") == caminho.rstrip("/") and metodo in metodos:
                return metodos[metodo]
        return None

    def _texto_docs(self, doc: dict) -> str:
        return (doc.get("content") or {}).get("body") or ""

    def _texto_endpoint(self, doc: dict) -> str:
        api = doc.get("api") or {}
        metodo = (api.get("method") or "").upper()
        caminho = api.get("path") or ""
        op = self._operacao_do_endpoint(doc) or {}
        descricao = op.get("description") or op.get("summary") or ""
        partes = [f"# {doc.get('title', '')}", "", f"**Endpoint:** `{metodo} {caminho}`", ""]
        parametros = op.get("parameters") or []
        if parametros:
            partes.append("**Parametros:**")
            for p in parametros:
                nome = p.get("name", "")
                local = p.get("in", "")
                obrig = "obrigatorio" if p.get("required") else "opcional"
                partes.append(f"- `{nome}` ({local}, {obrig})")
            partes.append("")
        partes.append(descricao)
        return "\n".join(partes).strip()

    def extrair_um(self, url: str, tipo: str) -> Artigo | None:
        html = self._baixar(url)
        doc = self._ssr_document(html)
        if not doc or not doc.get("title"):
            return None

        if tipo == "reference":
            texto = self._texto_endpoint(doc)
            api = doc.get("api") or {}
            op = self._operacao_do_endpoint(doc) or {}
            categoria = ", ".join(op.get("tags") or []) or _categoria_de_uri(
                (doc.get("category") or {}).get("uri"), "Referencia API"
            )
            metadados = {"metodo": api.get("method", ""), "caminho": api.get("path", "")}
        else:
            texto = self._texto_docs(doc)
            categoria = _categoria_de_uri((doc.get("category") or {}).get("uri"), "Portal do Desenvolvedor")
            metadados = {}

        if len(texto) < 40:
            return None

        return Artigo(
            artigo_id=doc.get("slug") or url.rsplit("/", 1)[-1],
            titulo=doc["title"],
            texto=texto,
            url=url,
            categoria=categoria,
            pasta="Portal do Desenvolvedor",
            atualizado_em=doc.get("updated_at", ""),
            metadados=metadados,
        )

    def extrair_tudo(
        self,
        saida: Path | None = None,
        verbose: bool = True,
        modo: str = "w",
        incluir_changelog: bool = False,
    ) -> int:
        saida = Path(saida or config.ARQUIVO_ARTIGOS)
        saida.parent.mkdir(parents=True, exist_ok=True)
        pares = self.urls_do_sitemap(incluir_changelog=incluir_changelog)
        if verbose:
            print(f"[dev] {len(pares)} paginas no sitemap")
        total = 0
        with saida.open(modo, encoding="utf-8") as f:
            for url, tipo in pares:
                try:
                    artigo = self.extrair_um(url, tipo)
                except Exception as e:  # noqa
                    if verbose:
                        print(f"  ! erro em {url}: {e}")
                    continue
                if artigo is None:
                    continue
                f.write(json.dumps(asdict(artigo), ensure_ascii=False) + "\n")
                f.flush()
                total += 1
                if verbose:
                    print(f"  + [{tipo}] {artigo.titulo[:70]}")
        if verbose:
            print(f"[dev] Total extraido: {total} paginas -> {saida}")
        return total
