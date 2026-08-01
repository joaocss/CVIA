# CVIA — guia para o Claude Code

Assistente de suporte do **CV CRM** (CRM do mercado imobiliário) baseado em **RAG**:
responde perguntas usando **só** a documentação oficial do CV (Base de Ajuda Freshdesk,
Portal do Desenvolvedor e docs locais por allowlist), citando as fontes e recusando de
forma honesta quando a base não cobre a dúvida (anti-alucinação).

## Como rodar

```bash
# 1. dependências
pip install -r requirements.txt

# 2. .env (copie de .env.example). Para começar de graça/offline:
#    CVIA_EMBEDDING_PROVEDOR=mock   CVIA_LLM_PROVEDOR=mock
#    Produção: openai (embeddings + LLM) com OPENAI_API_KEY

# 3. extrair a base (crawler Freshdesk + Portal do Dev) -> dados/artigos.jsonl
python -m cvia.cli extrair

# 4. ingerir: chunk + embeddings -> índice vetorial + ACERVO de artigos íntegros
python -m cvia.cli ingerir dados/artigos.jsonl

# 5a. perguntar no terminal
python -m cvia.cli perguntar "como criar uma reserva?"
# 5b. chat web (multimodal) em http://localhost:8000
uvicorn app:app --reload
```

`info` mostra provedores e tamanho do índice. Amostra versionada: `dados/artigos_amostra.jsonl`.

## Arquitetura (pipeline RAG)

Extração → **limpeza** (HTML → markdown, **preservando imagens inline e listas**) →
**chunking** (só p/ busca) → embeddings → repositório vetorial. Na consulta:
guardrail de entrada → mascara PII → embedding → busca top-K (cosseno) →
grounding (limiar) → resolve o **artigo íntegro** no acervo → prompt → LLM →
guardrail de saída.

Camadas com interfaces trocáveis (`Protocol` em `cvia/ia/tipos.py`):

- `cvia/ia/` — fábricas de embeddings/LLM por env. Provedores: `mock` (offline), `local`
  (sentence-transformers, bom em PT-BR), `openai`.
- `cvia/rag/` — núcleo:
  - `chunker.py` quebra o artigo em trechos (o `limpar_ruido` remove imagens **só do chunk**,
    que serve à busca; o artigo íntegro mantém as imagens).
  - `acervo.py` (`AcervoArtigos`) — guarda o **texto completo com imagens** por `artigo_id`
    em `dados/indice/artigos.jsonl`; gravado na ingestão, carregado na consulta.
  - `assistente.py` (`responder`) — orquestra; `resolver_artigos()` mapeia chunk → artigo
    íntegro; `REGRAS_SISTEMA` pede um **texto complementar didático** curto (o passo a passo
    completo com prints é reapresentado abaixo pela interface).
  - `guardrails.py`, `ingestao.py`, `repositorio.py` (local numpy) /
    `repositorio_postgres.py` (pgvector), `verificador.py` (heurística de fidelidade).
- `cvia/extracao/` — `extrator_freshdesk.py`, `extrator_desenvolvedor.py`,
  `extrator_local.py` (allowlist) e `limpeza.py`.
- `app.py` — API FastAPI + chat web (`static/index.html`) + painel `/admin`.
- `config.py` — caminhos, provedores, parâmetros do RAG, limiares (tudo sobrescrevível por env).

## Apresentação multimodal (comportamento atual)

A resposta tem **duas partes**: (1) um **texto didático** curto gerado pelo LLM que orienta a
execução do serviço/tarefa/configuração, e (2) o **artigo na íntegra** renderizado logo abaixo
— com os **prints (imagens) inline**, seções, listas numeradas e notas, no padrão do CVrino.

Fluxo de imagens: `limpeza.py` converte `<img>` em `![alt](url)` na posição original (URL
remota do Freshdesk/CDN, absolutizada quando começa com `//`). `app.py` devolve o campo
`artigos` (texto íntegro) e `static/index.html` (`renderMarkdown`) renderiza markdown com
imagens, cabeçalhos e listas ordenadas/aninhadas.

> Importante: a base extraída **antes** desta mudança não tem imagens. Para vê-las é preciso
> **reextrair e reingerir** (`extrair` → `ingerir`).

## Convenções de código

- **Todo identificador em português, sem acentos**, no case idiomático da linguagem
  (Python: `snake_case`/`PascalCase`; JS: `camelCase`). Comentários em português.
- Segredos **só** por variável de ambiente (`.env`, nunca commitado). Nada de dado de
  cliente/credencial no índice nem no git.
- Guardrails e logs são **best-effort**: nunca podem derrubar a resposta.
- Ao mexer numa peça, respeitar a interface (`Protocol`) para não vazar acoplamento.

## Variáveis de ambiente principais

`CVIA_EMBEDDING_PROVEDOR` (mock|local|openai), `CVIA_LLM_PROVEDOR` (mock|openai),
`CVIA_REPOSITORIO` (local|postgres), `OPENAI_API_KEY`, `DATABASE_URL`,
`CVIA_TOP_K`, `CVIA_LIMIAR_GROUNDING`, `CVIA_ADMIN_TOKEN`. O provedor de embeddings
**tem de ser o mesmo** na ingestão e na consulta.
