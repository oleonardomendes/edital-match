"""Similaridade entre um requisito (ex.: "gestão de projetos de TI") e um trecho do CV.

Duas implementações com a mesma interface:

* ``LexicalSimilarity`` funciona sem modelo nenhum (testes, modo demo).
* ``EmbeddingSimilarity`` usa embeddings e é a recomendada em produção, porque
  entende que "liderança de squads" e "gestão de equipes" são parecidos.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

import numpy as np
from rapidfuzz import fuzz

from app.matching.embeddings import Embedder
from app.matching.text import tokens


class Similarity(Protocol):
    limiar: float

    def score(self, requisito: str, texto: str) -> float:
        """Retorna de 0 a 1 o quanto ``texto`` corresponde a ``requisito``."""


class LexicalSimilarity:
    limiar = 0.5

    def score(self, requisito: str, texto: str) -> float:
        """Fração das palavras do requisito presentes no texto (tolera erros de digitação)."""
        req, txt = tokens(requisito), tokens(texto)
        if not req or not txt:
            return 0.0
        achadas = sum(
            1 for r in req
            if r in txt or (len(r) >= 5 and any(fuzz.ratio(r, t) >= 88 for t in txt))
        )
        return achadas / len(req)


class EmbeddingSimilarity:
    def __init__(self, embedder: Embedder, limiar: float = 0.55) -> None:
        self.embedder = embedder
        self.limiar = limiar
        self._lexical = LexicalSimilarity()

    @lru_cache(maxsize=4096)
    def _vetor(self, texto: str) -> np.ndarray:
        v = np.asarray(self.embedder.embed([texto])[0], dtype=np.float32)
        n = np.linalg.norm(v)
        return v / n if n else v

    def score(self, requisito: str, texto: str) -> float:
        cos = float(self._vetor(requisito) @ self._vetor(texto))
        # O léxico continua valendo quando o termo aparece literalmente.
        return max(cos, self._lexical.score(requisito, texto))
