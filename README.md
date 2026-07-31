# CVIA — Assistente de Suporte do CV CRM (RAG)

Assistente que responde perguntas com base **exclusivamente** no conteúdo da
Base de Ajuda (`ajuda.cvcrm.com.br`), do Portal do Desenvolvedor
(`desenvolvedor.cvcrm.com.br`) e de documentos técnicos internos selecionados.
Arquitetura RAG em Python, portada e adaptada do projeto de referência
`SaaS_Escolar_IA`.

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

`python -m cvia.cli extrair` roda três fontes em sequência e salva tudo em
`dados/artigos.jsonl` (respeita intervalo entre requisições e usa um
*User-Agent* próprio):

1. **Base de Ajuda** (Freshdesk) — categoria → pasta → artigo.
2. **Portal do Desenvolvedor** (ReadMe.io) — via `sitemap.xml`: guias e
   referência de cada endpoint de API (método, parâmetros, descrição).
3. **Documentos locais** (`cvia/extracao/extrator_local.py`) — uma lista
   explícita de arquivos em `cvia/extracao/extradoc/`, não um scan da pasta
   inteira (alguns arquivos ali têm dados de cliente ou credenciais e nunca
   devem entrar no índice nem no git — veja o `.gitignore`).

```bash
python -m cvia.cli extrair                      # as 3 fontes
python -m cvia.cli extrair --sem-dev --sem-local # só a base de ajuda
python -m cvia.cli ingerir                       # usa dados/artigos.jsonl por padrão
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

## Rodando como API + chat web (deploy online)

`app.py` expõe o mesmo pipeline do CLI por HTTP (FastAPI) e serve uma
interface de chat (`static/index.html`) para testar visualmente, com as
cores/identidade do CV CRM (navy `#12344D` + verde `#00B389`):

```bash
pip install -r requirements.txt   # inclui fastapi + uvicorn + psycopg2-binary
uvicorn app:app --reload          # http://127.0.0.1:8000 → chat web
```

- `GET /` — interface de chat (HTML/CSS/JS puro, sem build step).
- `GET /health` — status do índice e provedores configurados.
- `POST /perguntar {"pergunta": "...", "historico": [...], "sessao_id": "..."}` — mesma resposta do `cli.py perguntar`, em JSON. `sessao_id` é gerado no navegador (localStorage) e serve pra agrupar "usuários" no painel antes de existir login de verdade.
- `GET /docs` — Swagger UI gerado automaticamente.

### Painel de gestor (`/admin`)

Dashboard de uso e qualidade — perguntas por dia, usuários mais ativos,
taxa de recusa, alertas de guardrail (PII/injection) e uma heurística de
possível alucinação (segunda chamada de LLM perguntando se a resposta se
sustenta nas fontes recuperadas — não é detecção garantida, é sinal pra
revisão humana).

Protegido por token temporário (`CVIA_ADMIN_TOKEN` no `.env`) até existir
autenticação de verdade via API do Freshdesk — nesse ponto, `usuario_id`/
`usuario_email` (hoje `null`, preenchidos automaticamente pelo backend)
substituem a sessão anônima em todo o painel sem mudar o resto do schema.
Sem o token configurado, `/admin/api/*` responde 403 e o painel fica
desabilitado.

Todo log de interação é *best-effort*: se o `DATABASE_URL` não estiver
configurado ou a escrita falhar, o assistente responde normalmente — só o
registro no painel é que fica de fora.

### Banco online (Postgres/pgvector via Supabase)

Por padrão o índice fica em `dados/indice/` (arquivo local). Para usar um
banco online (persistente entre deploys, necessário se for hospedar em algo
sem disco persistente):

```bash
# .env
CVIA_REPOSITORIO=postgres
DATABASE_URL=postgresql://usuario:senha@host:5432/postgres
```

`cvia/rag/repositorio_postgres.py` implementa a mesma interface do
repositório local (cria a extensão `vector`, a tabela e o índice HNSW
automaticamente na primeira conexão). Só faz sentido com embeddings OpenAI
(dimensão fixa 1536 na tabela — trocar de provedor de embeddings exige
recriar a tabela). Depois de configurar, rode `python -m cvia.cli ingerir`
normalmente — ele detecta o repositório pela env var.

### Deploy com Docker

```bash
docker build -t cvia .
docker run -p 8000:8000 --env-file .env cvia
```

O `docker-entrypoint.sh` roda `extrair` + `ingerir` automaticamente no
primeiro start se `dados/indice/vetores.npy` não existir (leva alguns minutos
na primeira vez). Para deploys seguintes mais rápidos, monte `dados/` como
volume persistente para reaproveitar o índice já gerado.

### Hospedagem

Qualquer host que rode um `Dockerfile` (Render, Railway, Fly.io, um VPS
próprio, etc.) serve. Passos que **exigem uma conta/serviço de terceiros** —
e por isso ficam fora do que a automação consegue fazer sozinha:

1. Criar a conta no provedor escolhido e conectar o repositório
   `github.com/joaocss/CVIA`.
2. Configurar as variáveis de ambiente do serviço (nunca commitar o `.env`):
   `OPENAI_API_KEY`, `CVIA_EMBEDDING_PROVEDOR=openai`, `CVIA_LLM_PROVEDOR=openai`.
3. Anexar um volume persistente em `/app/dados` (evita reingerir a cada deploy).
4. Se o assistente for ficar acessível para clientes externos (não só o time
   interno), revisar `cvia/extracao/extrator_local.py` antes: o repositório
   público não inclui `origemcv_leads.md` (relatório de bug interno) nem os
   arquivos com dados de cliente — eles só existem na máquina onde a extração
   local foi rodada, então um deploy a partir do GitHub já sai sem esse
   conteúdo por padrão.

## Estrutura

```
CVIA/
├── app.py                    # API HTTP (FastAPI) para deploy online
├── Dockerfile / docker-entrypoint.sh
├── config.py                 # caminhos, categorias, modelos, limiares
├── cvia/
│   ├── extracao/
│   │   ├── extrator_freshdesk.py     # crawler ajuda.cvcrm.com.br (categoria→pasta→artigo)
│   │   ├── extrator_desenvolvedor.py # crawler desenvolvedor.cvcrm.com.br (sitemap + ssr-props)
│   │   ├── extrator_local.py         # allowlist de documentos locais (extradoc/)
│   │   └── limpeza.py                # HTML → título + texto limpo
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
