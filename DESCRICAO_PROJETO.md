CVIA — Assistente de Suporte do CV CRM (RAG)

Visão geral
CVIA é um assistente virtual que responde perguntas de suporte técnico e de negócio do CV CRM (CRM do mercado imobiliário) baseando-se exclusivamente no conteúdo oficial da empresa. Em vez de responder por conhecimento genérico de um LLM, o assistente recupera trechos relevantes da documentação do CV, monta o contexto e só então gera a resposta — citando os artigos usados. Quando a dúvida não está coberta pela documentação, ele diz isso de forma honesta e sugere abrir atendimento, em vez de inventar (anti-alucinação). O projeto reaproveita e adapta a arquitetura RAG do projeto de referência SaaS_Escolar_IA, portada de TypeScript para Python e reorientada do domínio escolar para o domínio de suporte/integração do CV CRM.

Fontes de conhecimento
O índice é construído a partir de três fontes, unificadas em um mesmo formato de artigo:
1. Base de Ajuda (ajuda.cvcrm.com.br) — portal Freshdesk com 6 categorias de topo (Painel Corretor, Painel Gestor, Portal do Cliente, Perguntas Frequentes, Integrações e API, LGPD). Hierarquia categoria → pasta → artigo.
2. Portal do Desenvolvedor (desenvolvedor.cvcrm.com.br) — documentação técnica em ReadMe.io: guias e referência de cada endpoint de API (método, parâmetros, descrição), coletados via sitemap.
3. Documentos locais selecionados — uma allowlist explícita de arquivos internos (não um scan de pasta), justamente porque parte desse material contém dados de cliente ou credenciais que nunca devem entrar no índice nem no controle de versão.

Como funciona (pipeline RAG)
Extração → limpeza de HTML → chunking (quebra por seção "##" e por tamanho-alvo com sobreposição) → geração de embeddings → armazenamento no repositório vetorial. Na consulta: guardrail de entrada → mascaramento de PII → embedding da pergunta → busca vetorial top-K por similaridade de cosseno → verificação de grounding (se o melhor score for baixo, recusa honesta) → montagem do prompt com o contexto recuperado → geração pelo LLM → guardrail de saída → resposta com citação das fontes.

Arquitetura e stack
Python, em camadas com interfaces trocáveis (Protocol), o que permite trocar cada peça sem tocar no restante:
- Camada de IA: fábricas de embeddings e LLM que selecionam o provedor por variável de ambiente. Provedores de embeddings: mock (hashing, offline, sem chave de API, para testar o pipeline), local (sentence-transformers, gratuito e bom em PT-BR) e openai. LLM: mock e openai.
- Núcleo RAG: chunker, ingestão, guardrails e o pipeline do assistente.
- Repositório vetorial plugável: por padrão é um índice local (numpy + cosseno, arquivo em disco); alternativamente Postgres/pgvector (Supabase) para persistência entre deploys, com criação automática de extensão, tabela e índice HNSW.
- Extração: um crawler para o Freshdesk, outro para o Portal do Desenvolvedor e o extrator de documentos locais por allowlist.
- Interfaces: CLI (extrair, ingerir, perguntar, chat, info) e uma API HTTP em FastAPI (app.py) que expõe o mesmo pipeline e serve um chat web com a identidade visual do CV CRM (navy #12344D + verde #00B389).

Guardrails e privacidade
O assistente prioriza LGPD e robustez: mascara PII (e-mail, telefone, CPF) antes de enviar ao modelo e na saída, sinaliza tentativas de prompt injection e se recusa a responder fora da base. Todo log de interação é best-effort — se o banco não estiver configurado ou a escrita falhar, o assistente responde normalmente e apenas o registro do painel fica de fora.

Painel de gestor (/admin)
Dashboard de uso e qualidade: perguntas por dia, usuários mais ativos, taxa de recusa, alertas de guardrail (PII/injection) e uma heurística de possível alucinação (uma segunda chamada de LLM avalia se a resposta se sustenta nas fontes — sinal para revisão humana, não detecção garantida). Protegido por token temporário (CVIA_ADMIN_TOKEN) até existir autenticação de verdade via API do Freshdesk; sem o token, as rotas de admin respondem 403.

Deploy
Roda localmente via uvicorn ou containerizado (Dockerfile + docker-entrypoint.sh, que executa extração e ingestão no primeiro start). Hospedável em qualquer serviço que rode Dockerfile (Render, Railway, Fly.io, VPS). Para produção usa-se embeddings e LLM da OpenAI e um volume persistente em /app/dados para não reingerir a cada deploy. Segredos (OPENAI_API_KEY etc.) sempre por variável de ambiente, nunca commitados.

Status atual
Estrutura das fontes mapeada; núcleo RAG funcional (extração, chunk, embeddings, busca, resposta); guardrails de suporte; amostra real de artigos e pipeline testado de ponta a ponta com embeddings mock. Pendentes/opcionais: extração completa das três fontes, escolha e calibração do provedor de produção, recalibração do limiar de grounding com perguntas reais e, se necessário, troca do vector store local por pgvector/FAISS para escala.

Contexto de uso
Projeto do João Cosme, Analista de Integração N3 do CV CRM. O CVIA nasce para dar respostas rápidas e ancoradas na documentação oficial ao time de suporte e, futuramente, a clientes — reduzindo o esforço de garimpar artigos manualmente e mantendo consistência com a Base de Conhecimento do CV.
