"""Crawler da Base de Conhecimento do CV CRM (portal Freshdesk).

Hierarquia: categoria (/support/solutions/{id}) -> pasta
(/support/solutions/folders/{id}) -> artigo (/support/solutions/articles/{id}-slug).

Fluxo:
  1. Para cada categoria em config.CATEGORIAS, baixa a pagina e coleta os links
     de pastas e de artigos.
  2. Para cada pasta, baixa a pagina (com paginacao) e coleta todos os artigos.
  3. Para cada artigo, baixa e limpa o conteudo (limpeza.extrair_artigo).
  4. Salva incrementalmente em dados/artigos.jsonl (um artigo por linha).

Boas praticas: intervalo entre requisicoes, retentativas, User-Agent proprio.
Roda na maquina do usuario (nao neste ambiente, que bloqueia fetch por script).

Uso:  python -m cvia.cli extrair
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from pathlib import Path

import config
from ..ia.tipos import Artigo
from .limpeza import extrair_artigo

RE_ARTIGO = re.compile(r"/support/solutions/articles/(\d+)")
RE_PASTA = re.compile(r"/support/solutions/folders/(\d+)")


def _requests():
    try:
        import requests
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Pacote 'requests' nao instalado. Rode: pip install requests") from e
    return requests


class ExtratorFreshdesk:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or config.BASE_URL).rstrip("/")
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

    def _abs(self, href: str) -> str:
        if href.startswith("http"):
            return href
        return self.base_url + href

    def _links(self, html: str, regex: re.Pattern) -> list[str]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        vistos: dict[str, str] = {}
        for a in soup.find_all("a", href=True):
            if regex.search(a["href"]):
                url = self._abs(a["href"].split("#")[0])
                vistos[url] = url
        return list(vistos.values())

    def pastas_da_categoria(self, categoria_id: str) -> list[str]:
        html = self._baixar(f"{self.base_url}/support/solutions/{categoria_id}")
        return self._links(html, RE_PASTA)

    def artigos_da_pasta(self, pasta_url: str) -> list[str]:
        artigos: dict[str, str] = {}
        pagina = 1
        while True:
            url = pasta_url if pagina == 1 else f"{pasta_url}?page={pagina}"
            html = self._baixar(url)
            novos = self._links(html, RE_ARTIGO)
            antes = len(artigos)
            for u in novos:
                artigos[u] = u
            # sem novos artigos = fim da paginacao
            if len(artigos) == antes or pagina > 20:
                break
            pagina += 1
        return list(artigos.values())

    def _id_do_url(self, url: str) -> str:
        m = RE_ARTIGO.search(url)
        return m.group(1) if m else url

    def extrair_um(self, url: str, categoria: str = "", pasta: str = "") -> Artigo:
        html = self._baixar(url)
        dados = extrair_artigo(html)
        return Artigo(
            artigo_id=self._id_do_url(url),
            titulo=dados["titulo"],
            texto=dados["texto"],
            url=url,
            categoria=categoria,
            pasta=pasta,
            atualizado_em=dados.get("atualizado_em", ""),
            metadados={"autor": dados.get("autor", "")},
        )

    def extrair_tudo(self, saida: Path | None = None, verbose: bool = True, modo: str = "w") -> int:
        saida = Path(saida or config.ARQUIVO_ARTIGOS)
        saida.parent.mkdir(parents=True, exist_ok=True)
        vistos: set[str] = set()
        total = 0
        with saida.open(modo, encoding="utf-8") as f:
            for cat_id, cat_nome in config.CATEGORIAS.items():
                if verbose:
                    print(f"[categoria] {cat_nome} ({cat_id})")
                for pasta_url in self.pastas_da_categoria(cat_id):
                    for art_url in self.artigos_da_pasta(pasta_url):
                        if art_url in vistos:
                            continue
                        vistos.add(art_url)
                        try:
                            artigo = self.extrair_um(art_url, categoria=cat_nome)
                        except Exception as e:  # noqa
                            if verbose:
                                print(f"  ! erro em {art_url}: {e}")
                            continue
                        if len(artigo.texto) < 40:
                            continue
                        f.write(json.dumps(asdict(artigo), ensure_ascii=False) + "\n")
                        f.flush()
                        total += 1
                        if verbose:
                            print(f"  + {artigo.titulo[:70]}")
        if verbose:
            print(f"\nTotal extraido: {total} artigos -> {saida}")
        return total
