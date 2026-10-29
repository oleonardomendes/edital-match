"""Avaliação da recuperação de trechos (a etapa "R" do RAG).

Cada pergunta do gabarito lista trechos de texto que precisam aparecer na
resposta da busca. Uma pergunta conta como acerto em k quando algum dos k
primeiros trechos recuperados contém um dos textos esperados.

Métricas:
* acerto@k (hit rate): fração das perguntas com acerto nos k primeiros;
* MRR: média de 1/posição do primeiro trecho correto (1 = sempre em primeiro).

Também compara a busca híbrida com cada busca sozinha, para mostrar o ganho
da combinação.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import TrechoEdital
from app.matching.embeddings import Embedder
from app.matching.text import normalizar
from app.rag.busca import RRF_K, Resultado, _consulta_textual, buscar

GABARITO = Path(__file__).resolve().parent / "gabarito_busca.json"


def carregar_gabarito(conjunto: str) -> dict:
    return json.loads(GABARITO.read_text(encoding="utf-8"))[conjunto]


def _posicao(resultados: list[Resultado], esperados: list[str]) -> int | None:
    alvos = [normalizar(e) for e in esperados]
    for i, r in enumerate(resultados, start=1):
        t = normalizar(f"{r.secao} {r.texto}")
        if any(a in t for a in alvos):
            return i
    return None


def _so_vetor(session: Session, edital_id: int, pergunta: str, embedder: Embedder, k: int) -> list[Resultado]:
    vetor = embedder.embed([pergunta])[0]
    linhas = session.scalars(select(TrechoEdital).where(TrechoEdital.edital_id == edital_id)
                             .order_by(TrechoEdital.embedding.cosine_distance(vetor)).limit(k))
    return [Resultado(t.id, t.ordem, t.pagina, t.secao, t.texto) for t in linhas]


def _so_texto(session: Session, edital_id: int, pergunta: str, embedder: Embedder, k: int, norm: int = 0) -> list[Resultado]:
    q = _consulta_textual(pergunta)
    linhas = session.scalars(select(TrechoEdital).where(TrechoEdital.edital_id == edital_id, TrechoEdital.tsv.op("@@")(q))
                             .order_by(func.ts_rank_cd(TrechoEdital.tsv, q, norm).desc()).limit(k))
    return [Resultado(t.id, t.ordem, t.pagina, t.secao, t.texto) for t in linhas]


def avaliar_busca(session: Session, edital_id: int, perguntas: list[dict], embedder: Embedder, ks=(1, 3, 5),
                  rrf_k: int = RRF_K, norm: int = 0, candidatos: int = 20) -> dict:
    kmax = max(ks)
    metodos = {
        "hibrida": lambda q: buscar(session, edital_id, q, embedder, k=kmax, candidatos=candidatos, rrf_k=rrf_k, norm=norm),
        "vetorial": lambda q: _so_vetor(session, edital_id, q, embedder, kmax),
        "textual": lambda q: _so_texto(session, edital_id, q, embedder, kmax, norm),
    }
    total_trechos = session.scalar(select(func.count()).where(TrechoEdital.edital_id == edital_id))
    saida: dict = {"perguntas": len(perguntas), "trechos_indexados": total_trechos, "rrf_k": rrf_k, "norm": norm, "candidatos": candidatos, "metodos": {}, "erros_hibrida": []}
    for nome, busca in metodos.items():
        posicoes = []
        for p in perguntas:
            pos = _posicao(busca(p["pergunta"]), p["espera"])
            posicoes.append(pos)
            if nome == "hibrida" and (pos is None or pos > 3):
                saida["erros_hibrida"].append({"pergunta": p["pergunta"], "posicao": pos})
        m = {f"acerto@{k}": round(sum(1 for x in posicoes if x and x <= k) / len(perguntas), 3) for k in ks}
        m["mrr"] = round(sum(1 / x for x in posicoes if x) / len(perguntas), 3)
        saida["metodos"][nome] = m
    return saida
