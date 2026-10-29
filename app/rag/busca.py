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


def _consulta_textual(pergunta: str):
    # "ou" entre as palavras: um trecho não precisa ter todas para aparecer;
    # o ranking (ts_rank_cd) premia quem tem mais e mais próximas.
    # Só letras e números: "-" e aspas têm significado especial no websearch_to_tsquery.
    palavras = [p for p in re.sub(r"[^a-z0-9]+", " ", normalizar(pergunta)).split() if len(p) > 1]
    return func.websearch_to_tsquery("portuguese", " or ".join(palavras))


def buscar(session: Session, edital_id: int, pergunta: str, embedder: Embedder, k: int = 6, candidatos: int = 20) -> list[Resultado]:
    vetor = embedder.embed([pergunta])[0]
    por_vetor = session.scalars(
        select(TrechoEdital)
        .where(TrechoEdital.edital_id == edital_id)
        .order_by(TrechoEdital.embedding.cosine_distance(vetor))
        .limit(candidatos)
    ).all()

    q = _consulta_textual(pergunta)
    por_texto = session.scalars(
        select(TrechoEdital)
        .where(TrechoEdital.edital_id == edital_id, TrechoEdital.tsv.op("@@")(q))
        .order_by(func.ts_rank_cd(TrechoEdital.tsv, q).desc())
        .limit(candidatos)
    ).all()

    resultados: dict[int, Resultado] = {}
    for fonte, lista in (("vetor", por_vetor), ("texto", por_texto)):
        for posicao, t in enumerate(lista, start=1):
            r = resultados.setdefault(t.id, Resultado(t.id, t.ordem, t.pagina, t.secao, t.texto))
            r.score += 1 / (RRF_K + posicao)
            r.fontes.append(fonte)
    return sorted(resultados.values(), key=lambda r: r.score, reverse=True)[:k]


def formatar_contexto(resultados: list[Resultado]) -> str:
    """Trechos com página e seção, na ordem em que aparecem no edital."""
    partes = []
    for r in sorted(resultados, key=lambda r: r.ordem):
        cabecalho = f"[p. {r.pagina}" + (f" · {r.secao}" if r.secao else "") + "]"
        partes.append(f"{cabecalho}\n{r.texto}")
    return "\n\n".join(partes)
