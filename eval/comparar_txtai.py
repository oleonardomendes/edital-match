"""Comparativo de recuperação: busca do Edital Match x txtai.

Mesmo edital (TJ-AC, ~110 páginas), mesmos trechos (o chunking do projeto) e o
mesmo gabarito de 15 perguntas de eval/gabarito_busca.json. Muda só o motor de
busca. Mede acerto@1/3/5, MRR e tempo de indexação.

Uso:
    python -m eval.comparar_txtai --pasta dados_pncp --saida eval/resultados/comparativo_txtai.json
    # --so-hashing roda só a parte que não baixa modelos (útil sem internet)

Requer Postgres com pgvector (DATABASE_URL) para a busca do Edital Match e, para
o txtai e os embeddings semânticos: pip install txtai fastembed
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import Edital, criar_tabelas, engine
from app.extraction.documents import DocumentoInvalido, extrair_paginas
from app.matching.embeddings import criar_embedder
from app.rag.busca import Resultado, indexar
from app.rag.chunking import Trecho, dividir
from eval.busca import _posicao, avaliar_busca, carregar_gabarito

MODELO_MULTILINGUE = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
KS = (1, 3, 5)


def paginas_do_edital(pasta: Path) -> list[str]:
    paginas: list[str] = []
    for arq in sorted(pasta.iterdir()):
        try:
            paginas.extend(extrair_paginas(arq.name, arq.read_bytes()))
        except DocumentoInvalido:
            continue
    return paginas


def metricas(posicoes: list[int | None]) -> dict:
    n = len(posicoes)
    m = {f"acerto@{k}": round(sum(1 for p in posicoes if p and p <= k) / n, 3) for k in KS}
    m["mrr"] = round(sum(1 / p for p in posicoes if p) / n, 3)
    return m


def edital_match(paginas: list[str], perguntas: list[dict], provider: str) -> dict:
    """Indexa no Postgres (pgvector + full-text) e mede as três buscas do projeto."""
    kwargs = {"model": MODELO_MULTILINGUE} if provider == "fastembed" else {}
    emb = criar_embedder(provider, **kwargs)
    criar_tabelas()
    with Session(engine()) as s:
        e = Edital(nome_arquivo="comparativo-txtai", texto="", requisitos={})
        s.add(e)
        s.flush()
        t0 = time.perf_counter()
        n = indexar(s, e.id, paginas, emb)
        t_idx = time.perf_counter() - t0
        r = avaliar_busca(s, e.id, perguntas, emb, ks=KS)
        s.rollback()  # não deixa nada gravado
    return {"trechos": n, "indexacao_s": round(t_idx, 1), "metodos": r["metodos"]}


def txtai_avaliar(trechos: list[Trecho], perguntas: list[dict], config: dict) -> dict:
    from txtai import Embeddings

    emb = Embeddings(content=True, **config)
    t0 = time.perf_counter()
    emb.index([(i, t.texto_indexado, None) for i, t in enumerate(trechos)])
    t_idx = time.perf_counter() - t0
    posicoes = []
    for p in perguntas:
        achados = emb.search(p["pergunta"], max(KS))
        rs = []
        for a in achados:
            t = trechos[int(a["id"])]
            rs.append(Resultado(0, t.ordem, t.pagina, t.secao, t.texto))
        posicoes.append(_posicao(rs, p["espera"]))
    return {"indexacao_s": round(t_idx, 1), **metricas(posicoes), "posicoes": posicoes}


CONFIGS_TXTAI = {
    "txtai padrão (all-MiniLM-L6-v2, inglês)": {},
    "txtai só palavra-chave (BM25)": {"keyword": True},
    "txtai denso multilíngue": {"path": MODELO_MULTILINGUE},
    "txtai híbrido padrão (BM25 + all-MiniLM-L6-v2)": {"hybrid": True},
    "txtai híbrido multilíngue (BM25 + MiniLM multilíngue)": {"path": MODELO_MULTILINGUE, "hybrid": True},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", type=Path, required=True, help="pasta com os PDFs do edital")
    ap.add_argument("--conjunto", default="tjac_2024")
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--so-hashing", action="store_true")
    a = ap.parse_args()

    perguntas = carregar_gabarito(a.conjunto)["perguntas"]
    paginas = paginas_do_edital(a.pasta)
    trechos = dividir(paginas)
    out: dict = {"conjunto": a.conjunto, "perguntas": len(perguntas), "paginas": len(paginas), "trechos": len(trechos),
                 "maquina": platform.platform(), "resultados": {}}

    provedores = ["hashing"] if a.so_hashing else ["hashing", "fastembed"]
    for prov in provedores:
        r = edital_match(paginas, perguntas, prov)
        nome = "hashing (n-gramas)" if prov == "hashing" else "MiniLM multilíngue"
        for metodo, m in r["metodos"].items():
            out["resultados"][f"Edital Match {metodo} · {nome}"] = {"indexacao_s": r["indexacao_s"], **m}
        print(f"Edital Match ({prov}) ok", flush=True)

    if not a.so_hashing:
        for nome, cfg in CONFIGS_TXTAI.items():
            out["resultados"][nome] = txtai_avaliar(trechos, perguntas, cfg)
            print(f"{nome} ok", flush=True)

    print(f"\n{'método':62} {'@1':>6} {'@3':>6} {'@5':>6} {'MRR':>6} {'idx(s)':>7}")
    for nome, m in sorted(out["resultados"].items(), key=lambda kv: -kv[1]["mrr"]):
        print(f"{nome:62} {m['acerto@1']:6.2f} {m['acerto@3']:6.2f} {m['acerto@5']:6.2f} {m['mrr']:6.3f} {m['indexacao_s']:7.1f}")
    if a.saida:
        a.saida.parent.mkdir(parents=True, exist_ok=True)
        a.saida.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
