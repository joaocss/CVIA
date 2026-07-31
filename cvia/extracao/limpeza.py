"""Limpeza do HTML de um artigo do portal Freshdesk -> titulo + texto limpo.
Isola o corpo do artigo e descarta navegacao, rodape, bloco de feedback e
scripts. Converte o HTML para texto preservando titulos de secao (## ) e
listas, o que ajuda o chunker a respeitar a estrutura."""
from __future__ import annotations

import re


def _exige_bs4():
    try:
        from bs4 import BeautifulSoup  # noqa
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Pacote 'beautifulsoup4' nao instalado. Rode: pip install beautifulsoup4 lxml"
        ) from e


# Seletores onde costuma ficar o corpo do artigo no portal Freshdesk.
SELETORES_CORPO = [
    "div.article-body",
    "article .article-body",
    "#article-body",
    "article",
    "div.fw-article-content",
]


def _elemento_corpo(soup):
    for sel in SELETORES_CORPO:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el
    return soup.body or soup


def _para_texto(el) -> str:
    linhas: list[str] = []
    for tag in el.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "td"]):
        txt = tag.get_text(" ", strip=True)
        if not txt:
            continue
        nome = tag.name
        if nome in ("h1", "h2", "h3", "h4"):
            linhas.append("")
            linhas.append(f"## {txt}")
            linhas.append("")
        elif nome == "li":
            linhas.append(f"- {txt}")
        else:
            linhas.append(txt)
    texto = "\n".join(linhas)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def extrair_artigo(html: str) -> dict:
    """Retorna {'titulo', 'texto', 'autor', 'atualizado_em'} a partir do HTML."""
    _exige_bs4()
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    titulo = ""
    if soup.title:
        titulo = soup.title.get_text(strip=True).split(" : ")[0].strip()
    h_titulo = soup.select_one("h2.heading, h1.article-title, .article-title")
    if h_titulo and h_titulo.get_text(strip=True):
        titulo = h_titulo.get_text(strip=True)

    autor = ""
    meta_autor = soup.find("meta", attrs={"name": "author"})
    if meta_autor and meta_autor.get("content"):
        autor = meta_autor["content"].strip()

    # Remove blocos que nao sao conteudo antes de extrair o texto.
    for sel in ["nav", "footer", "header", "script", "style", "form",
                ".article-votes", ".article-feedback", ".related-articles"]:
        for tag in soup.select(sel):
            tag.decompose()

    corpo = _elemento_corpo(soup)
    texto = _para_texto(corpo)

    # corta a partir do bloco de feedback, se sobrou
    texto = re.split(r"este artigo foi util", texto, flags=re.IGNORECASE)[0].strip()
    return {"titulo": titulo, "texto": texto, "autor": autor, "atualizado_em": ""}
