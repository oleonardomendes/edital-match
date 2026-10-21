"""Geradores de embeddings.

* ``fastembed``: modelo multilíngue local (ONNX), sem custo por chamada.
* ``openai``: API de embeddings da OpenAI ou compatível.
* ``hashing``: vetor determinístico de n-gramas, sem modelo. Usado nos testes e
  como plano B; captura semelhança de grafia, não de significado.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

from app.matching.text import normalizar


class Embedder(Protocol):
    dim: int

    def embed(self, textos: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, textos: list[str]) -> list[list[float]]:
        out = []
        for texto in textos:
            v = np.zeros(self.dim, dtype=np.float32)
            t = f" {normalizar(texto)} "
            for i in range(len(t) - 2):
                h = int.from_bytes(hashlib.blake2b(t[i : i + 3].encode(), digest_size=4).digest(), "big")
                v[h % self.dim] += 1.0
            n = np.linalg.norm(v)
            out.append((v / n if n else v).tolist())
        return out


class FastEmbedEmbedder:
    def __init__(self, model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2") -> None:
        from fastembed import TextEmbedding  # dependência opcional

        self._model = TextEmbedding(model_name=model)
        self.dim = len(next(iter(self._model.embed(["teste"]))))

    def embed(self, textos: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(textos)]


class OpenAIEmbedder:
    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None, base_url: str | None = None) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self.dim = 1536 if "small" in model else 3072

    def embed(self, textos: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=textos)
        return [d.embedding for d in resp.data]


def criar_embedder(provider: str, **kwargs) -> Embedder:
    if provider == "fastembed":
        return FastEmbedEmbedder(**kwargs)
    if provider == "openai":
        return OpenAIEmbedder(**kwargs)
    if provider == "hashing":
        return HashingEmbedder()
    raise ValueError(f"Provider de embeddings desconhecido: {provider}")
