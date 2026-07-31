"""Provedor de embeddings local via sentence-transformers (opcional, offline
apos baixar o modelo). Bom modelo multilingue para PT-BR:
'paraphrase-multilingual-MiniLM-L12-v2' (384 dimensoes)."""
from __future__ import annotations

import config


class EmbeddingsLocal:
    def __init__(self, modelo: str | None = None) -> None:
        self.nome_modelo = modelo or config.MODELO_EMBEDDING_LOCAL
        self.nome = f"local:{self.nome_modelo}"
        self._modelo = None
        self.dimensao = 384  # ajustado apos carregar

    def _carregar(self):
        if self._modelo is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:  # pragma: no cover
                raise RuntimeError(
                    "Pacote 'sentence-transformers' nao instalado. "
                    "Rode: pip install sentence-transformers"
                ) from e
            self._modelo = SentenceTransformer(self.nome_modelo)
            self.dimensao = self._modelo.get_sentence_embedding_dimension()
        return self._modelo

    def gerar(self, texto: str) -> list[float]:
        return self.gerar_lote([texto])[0]

    def gerar_lote(self, textos: list[str]) -> list[list[float]]:
        modelo = self._carregar()
        vetores = modelo.encode(textos, normalize_embeddings=True)
        return [v.tolist() for v in vetores]
