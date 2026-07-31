# CVIA — Assistente de Suporte do CV CRM (RAG)

Assistente que responde perguntas com base **exclusivamente** no conteúdo da
Base de Conhecimento do CV CRM (`https://ajuda.cvcrm.com.br`). Arquitetura RAG
em Python, portada e adaptada do projeto de referência `SaaS_Escolar_IA`.

O núcleo roda **offline, sem chave de API** (embeddings *mock*), o que permite
testar o pipeline de ponta a ponta. Para produção, basta trocar o provedor de
embeddings/LLM por `local` (sentence-transformers) ou `openai`, via variável de
ambiente — sem alterar o restante do código.

## Instalação

```bash
cd CVIA
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Para usar embeddings semânticos de verdade, descomente no `requirements.txt`:
`sentence-transformers` (local, offline) ou `openai` (requer `OPENAI_API_KEY`).

## Uso rápido (com a amostra já incluída)

```bash
# 1) Gera o índice vetorial a partir da amostra real (3 artigos)
python -m cvia.cli ingerir dados/artigos_amostra.jsonl

# 2) Pergunta ao assistente
python -m cvia.cli perguntar "Quais campos preciso preencher para cadastrar um webhook?"

# 3) Conversa interativa
python -m cvia.cli chat

# status do índice e provedores
python -m cvia.cli info
```

## Extrair a base completa

O crawler percorre categoria → pasta → artigo do portal Freshdesk e salva tudo
em `dados/artigos.jsonl`. Roda na sua máquina (respeita intervalo entre
requisições e usa um *User-Agent* próprio):

```bash
python -m cvia.cli extrair
python -m cvia.cli ingerir              # usa dados/artigos.jsonl por padrão
python -m cvia.cli perguntar "..."
```

## Escolhendo os provedores

Tudo por variável de ambiente (ou arquivo `.env`, veja `.env.example`):

```bash
# embeddings: mock (padrão) | local | openai   — o MESMO na ingestão e na consulta
# llm:        mock (padrão) | openai
CVIA_EMBEDDING_PROVEDOR=local CVIA_LLM_PROVEDOR=openai python -m cvia.cli perguntar "..."
```

> Ao trocar o provedor de embeddings, **reingira** a base (os vetores mudam de
> escala/dimensão) e reavalie `CVIA_LIMIAR_GROUNDING`.

## Estrutura

```
CVIA/
├── config.py                 # caminhos, categorias, modelos, limiares
├── cvia/
│   ├── extracao/
│   │   ├── extrator_freshdesk.py   # crawler categoria→pasta→artigo
│   │   └── limpeza.py              # HTML → título + texto limpo
│   ├── ia/
│   │   ├── tipos.py                # interfaces (Protocol): embeddings, LLM, repositório
│   │   ├── fabrica_embeddings.py   # seleciona mock | local | openai
│   │   ├── fabrica_llm.py          # seleciona mock | openai
│   │   ├── provedor_mock.py        # embeddings por hashing + LLM mock (offline)
│   │   ├── provedor_local.py       # sentence-transformers (opcional)
│   │   └── provedor_openai.py      # OpenAI (opcional)
│   ├── rag/
│   │   ├── chunker.py              # quebra por seção (##) + tamanho-alvo
│   │   ├── ingestao.py             # artigo → chunk → embedding → repositório
│   │   ├── repositorio.py          # vector store local (numpy, cosseno)
│   │   ├── guardrails.py           # PII/LGPD + anti-injection
│   │   └── assistente.py           # pipeline de resposta (grounding + citações)
│   └── cli.py                      # extrair | ingerir | perguntar | chat | info
└── dados/
    ├── artigos_amostra.jsonl       # amostra real (versionada)
    ├── artigos.jsonl               # base completa (gerada pelo crawler)
    └── indice/                     # vetores persistidos (gerado)
```

Veja `CONTEXTO_PROJETO.md` para as decisões de arquitetura e o mapeamento a
partir do `SaaS_Escolar_IA`.
