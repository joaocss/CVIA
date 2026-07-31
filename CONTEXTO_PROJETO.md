# CVIA — Contexto do Projeto

## Objetivo

Assistente de suporte que responde perguntas **somente** com base na Base de
Conhecimento pública do CV CRM (`https://ajuda.cvcrm.com.br/support/home`), via
RAG (Retrieval-Augmented Generation). Mesma premissa do `SaaS_Escolar_IA`, porém
para o domínio de suporte/integração do CV CRM e em stack simplificada (Python).

Este repositório é o **scaffold de código + pipeline funcional** gerado a partir
do reaproveitamento do projeto de referência. As instruções e o contexto formais
do projeto (quando você criá-lo individualmente) podem partir deste documento.

## Decisões desta versão

1. **Stack simplificada para Python** (sem Next.js/Supabase). O núcleo RAG do
   `SaaS_Escolar_IA` (TypeScript) foi portado para Python, preservando a mesma
   arquitetura de camadas e as interfaces trocáveis.
2. **Base única** (sem multi-tenant `escolaId`). A base de ajuda do CV é uma só;
   removida toda a lógica de isolamento por escola.
3. **Domínio de suporte**, não escola. Removidos BNCC, tutor infantil didático e
   guardrails de segurança infantil. No lugar: assistente de suporte objetivo,
   guardrails de **LGPD/PII** e **anti-injection**, e recusa honesta quando a
   dúvida não está na base (anti-alucinação).
4. **Vector store local** (numpy + cosseno), sem banco externo — roda em qualquer
   máquina. A interface `RepositorioTrechos` permite trocar por FAISS/Chroma/
   pgvector depois, sem tocar no pipeline.
5. **Provedores plugáveis por env**: embeddings `mock | local | openai`; LLM
   `mock | openai`. O padrão `mock` roda offline para validar o pipeline.

## Arquitetura (fluxo)

```
Extração (Freshdesk)          Ingestão                    Consulta
─────────────────────         ──────────                  ────────
categoria → pasta → artigo    artigo → chunk → embedding  pergunta → guardrail
   ↓ limpeza HTML                ↓                            → embedding
artigos.jsonl  ───────────►  repositório vetorial  ◄──────  → busca top-K
                             (numpy, cosseno)                → grounding? 
                                                             → prompt + LLM
                                                             → guardrail saída
                                                             → resposta + citações
```

## Mapeamento a partir do `SaaS_Escolar_IA`

| SaaS_Escolar_IA (TS)                    | CVIA (Python)                     | Mudança |
|-----------------------------------------|-----------------------------------|---------|
| `src/ia/tipos.ts`                       | `cvia/ia/tipos.py`                | Protocols em vez de interfaces |
| `src/ia/fabricaEmbeddings.ts` / `fabricaLlm.ts` | `cvia/ia/fabrica_*.py`    | idêntico em espírito |
| `src/ia/provedorOpenAI/Mock/...`        | `cvia/ia/provedor_*.py`           | mock agora usa hashing (retrieval real) |
| `src/ia/guardrails.ts`                  | `cvia/rag/guardrails.py`          | tirou segurança infantil; manteve PII/injection |
| `src/rag/chunkerTexto.ts`               | `cvia/rag/chunker.py`             | quebra por seção `##` + tamanho |
| `src/rag/ingestao.ts`                   | `cvia/rag/ingestao.py`            | sem `escolaId`; embedding em lote |
| `src/rag/repositorioSupabase/Postgres`  | `cvia/rag/repositorio.py`         | vector store local numpy |
| `src/rag/tutor.ts`                      | `cvia/rag/assistente.py`          | tutor → assistente de suporte |
| `src/rag/perguntar.ts`                  | `cvia/cli.py`                     | vira CLI (extrair/ingerir/perguntar/chat) |
| —                                       | `cvia/extracao/*`                 | novo: crawler Freshdesk |

## A base de ajuda (mapeada)

Portal Freshdesk. Categorias de topo:

- Painel Corretor — `157000076361`
- Painel Gestor — `157000111527`
- Portal do Cliente — `157000111528`
- Perguntas Frequentes — `157000312457`
- Integrações e API — `157000312462`
- LGPD — `157000312466`

Padrão de URL: categoria `/support/solutions/{id}` → pasta
`/support/solutions/folders/{id}` → artigo `/support/solutions/articles/{id}-slug`.
O corpo do artigo vem em `div.article-body`; o bloco "Este artigo foi útil?"
marca o fim do conteúdo.

## Status

- [x] Estrutura da base mapeada (categorias, pastas, artigos)
- [x] Núcleo RAG em Python (extração, chunk, embeddings, busca, resposta)
- [x] Guardrails de suporte (PII/LGPD + anti-injection)
- [x] Amostra real de 3 artigos + pipeline testado de ponta a ponta (mock)
- [ ] Extração completa da base (`python -m cvia.cli extrair` na sua máquina)
- [ ] Escolher provedor de produção (local vs. openai) e recalibrar o limiar
- [ ] (Opcional) trocar vector store local por FAISS/Chroma para escala

## Próximos passos sugeridos

1. Rodar o crawler completo e ingerir a base inteira.
2. Definir o provedor de embeddings de produção (recomendado começar por
   `local` com `paraphrase-multilingual-MiniLM-L12-v2`, gratuito e bom em PT-BR).
3. Recalibrar `CVIA_LIMIAR_GROUNDING` com perguntas reais de suporte.
4. Quando criar o projeto formal do CVIA, usar este documento como base de
   contexto/instruções.
