#!/bin/sh
# Se o indice estiver vazio (primeiro deploy / volume vazio / banco novo),
# roda extracao + ingestao antes de subir o servidor. Leva alguns minutos
# na primeira vez. Funciona tanto com CVIA_REPOSITORIO=local (arquivo) quanto
# =postgres (Supabase/pgvector) — a checagem e feita pelo proprio pipeline.
set -e

INDICE_VAZIO=$(python -c "
from cvia.rag.fabrica_repositorio import criar_repositorio
print('vazio' if criar_repositorio().carregar().total == 0 else 'ok')
")

if [ "$INDICE_VAZIO" = "vazio" ]; then
  echo "[entrypoint] indice vazio, rodando extracao + ingestao..."
  python -m cvia.cli extrair
  python -m cvia.cli ingerir
else
  echo "[entrypoint] indice encontrado, pulando extracao/ingestao."
fi

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
