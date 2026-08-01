"""Configuracao central do CVIA (assistente de suporte da base de conhecimento
do CV CRM). Um unico ponto para caminhos, parametros de extracao, modelos e
limiares do RAG. Valores podem ser sobrescritos por variaveis de ambiente
(carregadas de um arquivo .env, se existir)."""
from __future__ import annotations

import os
from pathlib import Path

# --- Caminhos ---------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent
DIR_DADOS = RAIZ / "dados"
DIR_BRUTO = DIR_DADOS / "bruto"                      # HTML/artigos crus do crawler
DIR_INDICE = DIR_DADOS / "indice"                    # vetores persistidos
ARQUIVO_ARTIGOS = DIR_DADOS / "artigos.jsonl"        # base completa (gerada pela extracao)
ARQUIVO_ACERVO = DIR_INDICE / "artigos.jsonl"        # artigos INTEGROS (texto+imagens) p/ reapresentacao
ARQUIVO_AMOSTRA = DIR_DADOS / "artigos_amostra.jsonl"  # amostra real versionada no repo

# --- Base de ajuda (Freshdesk) ----------------------------------------------
BASE_URL = "https://ajuda.cvcrm.com.br"
# Portal do desenvolvedor (ReadMe.io) -----------------------------------------
BASE_URL_DEV = "https://desenvolvedor.cvcrm.com.br"
# Categorias de topo da base de conhecimento (id -> rotulo amigavel).
CATEGORIAS: dict[str, str] = {
    "157000076361": "Painel Corretor",
    "157000111527": "Painel Gestor",
    "157000111528": "Portal do Cliente",
    "157000312457": "Perguntas Frequentes",
    "157000312462": "Integracoes e API",
    "157000312466": "LGPD",
}
# Boas praticas de crawling: intervalo entre requisicoes e tentativas.
EXTRACAO_INTERVALO_S = float(os.getenv("CVIA_EXTRACAO_INTERVALO", "0.7"))
EXTRACAO_TENTATIVAS = int(os.getenv("CVIA_EXTRACAO_TENTATIVAS", "3"))
EXTRACAO_USER_AGENT = os.getenv(
    "CVIA_USER_AGENT",
    "CVIA-bot/1.0 (assistente interno de suporte; contato: suporte@cvcrm.com.br)",
)

# --- Provedores de IA -------------------------------------------------------
# Embeddings e LLM tem fabrica propria; o provedor e escolhido por env.
#   CVIA_EMBEDDING_PROVEDOR = mock | local | openai   (padrao: mock)
#   CVIA_LLM_PROVEDOR       = mock | openai           (padrao: mock)
# O provedor de embeddings DEVE ser o mesmo na ingestao e na consulta.
EMBEDDING_PROVEDOR = os.getenv("CVIA_EMBEDDING_PROVEDOR", "mock").lower()
LLM_PROVEDOR = os.getenv("CVIA_LLM_PROVEDOR", "mock").lower()

MODELO_EMBEDDING_OPENAI = os.getenv("CVIA_MODELO_EMBEDDING_OPENAI", "text-embedding-3-small")
MODELO_EMBEDDING_LOCAL = os.getenv(
    "CVIA_MODELO_EMBEDDING_LOCAL", "paraphrase-multilingual-MiniLM-L12-v2"
)
MODELO_LLM_OPENAI = os.getenv("CVIA_MODELO_LLM_OPENAI", "gpt-4o-mini")
DIMENSAO_MOCK = int(os.getenv("CVIA_DIMENSAO_MOCK", "512"))

# --- Repositorio de trechos (vector store) -----------------------------------
#   CVIA_REPOSITORIO = local (padrao, arquivo numpy) | postgres (Supabase/pgvector)
# So faz sentido usar "postgres" com embeddings=openai (dimensao fixa 1536 na
# tabela). DATABASE_URL vem do .env (nunca commitar valor real).
REPOSITORIO_PROVEDOR = os.getenv("CVIA_REPOSITORIO", "local").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "")

# --- Parametros do RAG ------------------------------------------------------
CHUNK_TAMANHO_ALVO = int(os.getenv("CVIA_CHUNK_TAMANHO", "900"))
CHUNK_SOBREPOSICAO = int(os.getenv("CVIA_CHUNK_SOBREPOSICAO", "150"))
TOP_K = int(os.getenv("CVIA_TOP_K", "4"))
# Limiar minimo de similaridade para considerar que ha base na documentacao.
# Ajuste conforme o provedor de embeddings (mock/local/openai tem escalas
# diferentes). Abaixo disso o assistente responde que nao encontrou na base.
LIMIAR_GROUNDING = float(os.getenv("CVIA_LIMIAR_GROUNDING", "0.18"))
# Acima do limiar de grounding mas abaixo deste, a resposta e sinalizada no
# painel como "grounding fraco" (risco maior de a LLM ter completado com
# conhecimento proprio em vez de so a fonte) — heuristica, nao deteccao real.
LIMIAR_CONFIANCA = float(os.getenv("CVIA_LIMIAR_CONFIANCA", "0.35"))

# --- Painel de gestor / observabilidade --------------------------------------
# Token temporario para proteger /admin ate a autenticacao via API do
# Freshdesk existir. Gere um valor forte e configure via env — nunca deixe o
# padrao em producao (fica vazio = painel desabilitado).
ADMIN_TOKEN = os.getenv("CVIA_ADMIN_TOKEN", "")
# Roda uma segunda chamada de LLM (barata, max_tokens baixo) apos cada
# resposta nao recusada, perguntando se a resposta se sustenta nas fontes.
# Desliga se quiser cortar custo/latencia.
VERIFICAR_FIDELIDADE = os.getenv("CVIA_VERIFICAR_FIDELIDADE", "true").lower() != "false"
