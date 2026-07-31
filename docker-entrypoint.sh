#!/bin/sh
# Se o indice vetorial nao existir ainda (primeiro deploy / volume vazio),
# roda extracao + ingestao antes de subir o servidor. Leva alguns minutos
# na primeira vez; deploys seguintes (com volume persistente) pulam direto
# pro uvicorn.
set -e

if [ ! -f "dados/indice/vetores.npy" ]; then
  echo "[entrypoint] indice nao encontrado, rodando extracao + ingestao..."
  python -m cvia.cli extrair
  python -m cvia.cli ingerir
else
  echo "[entrypoint] indice encontrado, pulando extracao/ingestao."
fi

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
