"""Indexação e busca híbrida nos trechos do edital.

Duas buscas rodam no Postgres e os resultados são combinados:

* **vetorial** (pgvector): acha trechos com significado parecido, mesmo com
  outras palavras ("tempo de atuação" ~ "experiência profissional");
* **textual** (full-text search em português): acha termos exatos que o
  vetor pode diluir, como "PMP", "ITIL" ou "art. 67".

A combinação usa Reciprocal Rank Fusion (RRF): cada busca vota pela posição
do trecho no seu ranking, sem precisar comparar escalas de score diferentes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import TrechoEdital
from app.matching.embeddings import Embedder
from app.matching.text import normalizar
from app.rag.chunking import Trecho, dividir

RRF_K = 60
# Normalização do ts_rank_cd (bits do Postgres): 0 = nenhuma; 1 = divide por 1 + log(tamanho do trecho).
RANK_NORM = 0


@dataclass
class Resultado:
    id: int
    ordem: int
    pagina: int
    secao: str
    texto: str
    score: float = 0.0
    fontes: list[str] = field(default_factory=list)


def indexar(session: Session, edital_id: int, paginas: list[str], embedder: Embedder, lote: int = 64) -> int:
    """Apaga o índice antigo do edital e grava os trechos com embedding."""
    session.execute(delete(TrechoEdital).where(TrechoEdital.edital_id == edital_id))
    trechos: list[Trecho] = dividir(paginas)
    for i in range(0, len(trechos), lote):
        parte = trechos[i : i + lote]
        vetores = embedder.embed([t.texto_indexado for t in parte])
        session.add_all(
            TrechoEdital(edital_id=edital_id, ordem=t.ordem, pagina=t.pagina, secao=t.secao, texto=t.texto,
                         texto_busca=normalizar(t.texto_indexado), embedding=v)
            for t, v in zip(parte, vetores)
        )
    session.flush()
    return len(trechos)


def tem_indice(session: Session, edital_id: int) -> bool:
    return session.scalar(select(func.count()).where(TrechoEdital.edital_id == edital_id)) > 0


def _palavras(pergunta: str) -> list[str]:
    # Só letras e números: "-" e aspas têm significado especial no websearch_to_tsquery.
    return [p for p in re.sub(r"[^a-z0-9]+", " ", normalizar(pergunta)).split() if len(p) > 1]


def _consulta_textual(pergunta: str, todas: bool = False):
    """Consulta de texto: com todas as palavras (E) ou com qualquer uma (OU)."""
    return func.websearch_to_tsquery("portuguese", (" " if todas else " or ").join(_palavras(pergunta)))


def busca_textual(session: Session, edital_id: int, pergunta: str, limite: int, norm: int | None = None) -> list[TrechoEdital]:
    """Primeiro os trechos com todas as palavras da pergunta; depois, os que têm só algumas.

    Só com "OU", trechos de tabela que repetem "experiência" e "profissional"
    dezenas de vezes ganham de um parágrafo que responde à pergunta inteira.
    """
    norm = RANK_NORM if norm is None else norm
    saida: list[TrechoEdital] = []
    for todas in (True, False):
        q = _consulta_textual(pergunta, todas)
        consulta = (select(TrechoEdital)
                    .where(TrechoEdital.edital_id == edital_id, TrechoEdital.tsv.op("@@")(q))
                    .order_by(func.ts_rank_cd(TrechoEdital.tsv, q, norm).desc())
                    .limit(limite))
        vistos = {t.id for t in saida}
        saida += [t for t in session.scalars(consulta) if t.id not in vistos]
        if len(saida) >= limite:
            break
    return saida[:limite]


def buscar(session: Session, edital_id: int, pergunta: str, embedder: Embedder, k: int = 6, candidatos: int = 20,
           rrf_k: int | None = None, norm: int | None = None) -> list[Resultado]:
    rrf_k = RRF_K if rrf_k is None else rrf_k
    norm = RANK_NORM if norm is None else norm
    vetor = embedder.embed([pergunta])[0]
    por_vetor = session.scalars(
        select(TrechoEdital)
        .where(TrechoEdital.edital_id == edital_id)
        .order_by(TrechoEdital.embedding.cosine_distance(vetor))
        .limit(candidatos)
    ).all()

    por_texto = busca_textual(session, edital_id, pergunta, candidatos, norm)

    resultados: dict[int, Resultado] = {}
    for fonte, lista in (("vetor", por_vetor), ("texto", por_texto)):
        for posicao, t in enumerate(lista, start=1):
            r = resultados.setdefault(t.id, Resultado(t.id, t.ordem, t.pagina, t.secao, t.texto))
            r.score += 1 / (rrf_k + posicao)
            r.fontes.append(fonte)
    return sorted(resultados.values(), key=lambda r: r.score, reverse=True)[:k]


def formatar_contexto(resultados: list[Resultado]) -> str:
    """Trechos com página e seção, na ordem em que aparecem no edital."""
    partes = []
    for r in sorted(resultados, key=lambda r: r.ordem):
        cabecalho = f"[p. {r.pagina}" + (f" · {r.secao}" if r.secao else "") + "]"
        partes.append(f"{cabecalho}\n{r.texto}")
    return "\n\n".join(partes)
