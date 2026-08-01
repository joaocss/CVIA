"""Limpeza do HTML de um artigo do portal Freshdesk -> titulo + texto limpo.
Isola o corpo do artigo e descarta navegacao, rodape, bloco de feedback e
scripts. Converte o HTML para MARKDOWN preservando a estrutura de leitura:
titulos de secao (## / ###), listas ordenadas (1.) e nao ordenadas (-), notas
aninhadas, blocos de codigo (```) e — o ponto central do modo multimodal — as
imagens inline (![alt](url)) na MESMA posicao em que aparecem no artigo.

Assim o artigo pode ser reapresentado na integra (texto + prints) como o
CVrino faz, em vez de virar so um bloco de texto sem as telas do passo a passo.
"""
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

# Tags que nunca sao conteudo do artigo.
TAGS_IGNORADAS = {"script", "style", "nav", "footer", "header", "form", "noscript"}


def _elemento_corpo(soup):
    for sel in SELETORES_CORPO:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el
    return soup.body or soup


def _absolutizar(url: str) -> str:
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    return url


def _imagem_markdown(tag) -> str:
    """<img> -> ![alt](url). Cobre lazy-load (data-src/data-original) do Freshdesk."""
    src = ""
    for attr in ("data-original", "data-src", "src"):
        valor = tag.get(attr)
        if valor and not valor.strip().startswith("data:"):
            src = valor
            break
    if not src:
        return ""
    alt = (tag.get("alt") or "").strip()
    return f"![{alt}]({_absolutizar(src)})"


def _texto_inline(el) -> str:
    """Texto de um elemento preservando imagens (inline) e links [texto](url)."""
    partes: list[str] = []
    for filho in el.children:
        nome = getattr(filho, "name", None)
        if nome is None:  # NavigableString
            txt = str(filho)
            if txt.strip():
                partes.append(txt)
        elif nome in TAGS_IGNORADAS:
            continue
        elif nome == "img":
            md = _imagem_markdown(filho)
            if md:
                partes.append(f" {md} ")
        elif nome == "br":
            partes.append(" ")
        elif nome == "a":
            href = (filho.get("href") or "").strip()
            interno = _texto_inline(filho)
            if filho.find("img"):
                partes.append(interno)
            elif href.startswith("http") and interno:
                partes.append(f"[{interno}]({href})")
            else:
                partes.append(interno)
        else:
            partes.append(_texto_inline(filho))
    return re.sub(r"[ \t]{2,}", " ", "".join(partes)).strip()


def _texto_item(li) -> str:
    """Texto de um <li> ignorando sublistas (que sao tratadas a parte)."""
    partes: list[str] = []
    for filho in li.children:
        nome = getattr(filho, "name", None)
        if nome in ("ul", "ol"):
            continue
        if nome is None:
            if str(filho).strip():
                partes.append(str(filho))
        elif nome == "img":
            md = _imagem_markdown(filho)
            if md:
                partes.append(f" {md} ")
        else:
            partes.append(_texto_inline(filho))
    return re.sub(r"[ \t]{2,}", " ", "".join(partes)).strip()


def _emitir_lista(el, linhas: list[str], ordenada: bool, nivel: int) -> None:
    recuo = "  " * nivel
    indice = 1
    for li in el.find_all("li", recursive=False):
        marcador = f"{indice}. " if ordenada else "- "
        texto = _texto_item(li)
        if texto:
            linhas.append(f"{recuo}{marcador}{texto}")
        for sub in li.find_all(["ul", "ol"], recursive=False):
            _emitir_lista(sub, linhas, ordenada=(sub.name == "ol"), nivel=nivel + 1)
        indice += 1


def _tem_bloco(el) -> bool:
    return el.find(
        ["p", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "div", "table", "pre", "img", "li"]
    ) is not None


def _percorrer(el, linhas: list[str], nivel: int = 0) -> None:
    for filho in el.children:
        nome = getattr(filho, "name", None)
        if nome is None or nome in TAGS_IGNORADAS:
            continue
        if nome in ("h1", "h2", "h3"):
            t = _texto_inline(filho)
            if t:
                linhas += ["", f"## {t}", ""]
        elif nome in ("h4", "h5", "h6"):
            t = _texto_inline(filho)
            if t:
                linhas += ["", f"### {t}", ""]
        elif nome in ("ul", "ol"):
            _emitir_lista(filho, linhas, ordenada=(nome == "ol"), nivel=nivel)
        elif nome == "pre":
            t = filho.get_text("\n", strip=False).strip("\n")
            if t.strip():
                linhas += ["", "```", t, "```", ""]
        elif nome == "img":
            md = _imagem_markdown(filho)
            if md:
                linhas += ["", md, ""]
        elif nome in ("p", "blockquote", "td", "th", "figcaption", "caption"):
            t = _texto_inline(filho)
            if t:
                linhas.append(t)
        elif nome in ("div", "section", "article", "figure", "table", "tr", "tbody", "thead", "span"):
            if _tem_bloco(filho):
                _percorrer(filho, linhas, nivel)
            else:
                t = _texto_inline(filho)
                if t:
                    linhas.append(t)
        else:
            _percorrer(filho, linhas, nivel)


def _para_texto(el) -> str:
    linhas: list[str] = []
    _percorrer(el, linhas)
    texto = "\n".join(linhas)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def extrair_artigo(html: str) -> dict:
    """Retorna {'titulo', 'texto', 'autor', 'atualizado_em'} a partir do HTML.
    O 'texto' vem em markdown com imagens inline (![alt](url))."""
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
