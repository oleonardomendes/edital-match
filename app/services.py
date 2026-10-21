"""Montagem das dependências a partir da configuração."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.extraction.llm import LLM, criar_llm
from app.matching.embeddings import Embedder, criar_embedder
from app.matching.scorer import Scorer
from app.matching.similarity import EmbeddingSimilarity, LexicalSimilarity
from app.schemas import PerfilCandidato


@lru_cache
def get_llm() -> LLM:
    s = get_settings()
    return criar_llm(s.llm_provider, s.llm_model, s.llm_api_key, s.llm_base_url)


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    kwargs = {"model": s.embedding_model} if s.embedding_model else {}
    return criar_embedder(s.embedding_provider, **kwargs)


def get_scorer() -> Scorer:
    s = get_settings()
    # Embeddings de hashing não entendem significado; nesse caso o léxico é melhor.
    if s.embedding_provider == "hashing":
        return Scorer(LexicalSimilarity())
    return Scorer(EmbeddingSimilarity(get_embedder()))


def texto_para_busca(p: PerfilCandidato) -> str:
    """Resumo do candidato usado no embedding da busca semântica."""
    partes = [f"{f.curso}" for f in p.formacoes]
    partes += [f"{e.cargo}. {e.descricao} {' '.join(e.tecnologias)}" for e in p.experiencias]
    partes += [c.nome for c in p.certificacoes]
    partes += p.competencias
    return "\n".join(partes)
