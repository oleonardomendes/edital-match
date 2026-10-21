"""Avalia o matcher contra o gabarito humano.

Modos:
  gabarito  usa as extrações corretas (escritas à mão) e mede só o motor de score.
  llm       extrai os PDFs com o LLM configurado e mede a cadeia inteira.

Uso:
  python -m eval.run_eval                 # modo gabarito
  python -m eval.run_eval --modo llm      # precisa de LLM_PROVIDER e LLM_API_KEY
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

from app.config import get_settings
from app.extraction.documents import extrair_texto
from app.extraction.extractor import Extractor, MemoryCache
from app.matching.scorer import Scorer
from app.schemas import PerfilCandidato, RequisitosEdital, StatusCriterio
from app.services import get_llm, get_scorer
from samples.candidatos import CANDIDATOS

RAIZ = Path(__file__).resolve().parent.parent
PDFS = RAIZ / "samples" / "pdfs"


def carregar(modo: str) -> tuple[RequisitosEdital, list[PerfilCandidato]]:
    if modo == "gabarito":
        edital = RequisitosEdital.model_validate_json(
            (RAIZ / "samples" / "gabarito" / "edital_vale_verde.json").read_text(encoding="utf-8"))
        return edital, [PerfilCandidato.model_validate(c["perfil"]) for c in CANDIDATOS]
    ext = Extractor(get_llm(), MemoryCache())
    ler = lambda nome: extrair_texto(nome, (PDFS / nome).read_bytes())  # noqa: E731
    edital = ext.edital(ler("edital_vale_verde.pdf"))
    return edital, [ext.candidato(ler(c["arquivo"])) for c in CANDIDATOS]


def ndcg(obtida: list[str], esperada: list[str]) -> float:
    """NDCG da ordem dos aptos: 1,0 quando a ordem é idêntica à do gabarito."""
    rel = {n: len(esperada) - i for i, n in enumerate(esperada)}
    dcg = sum(rel.get(n, 0) / math.log2(i + 2) for i, n in enumerate(obtida[: len(esperada)]))
    idcg = sum(rel[n] / math.log2(i + 2) for i, n in enumerate(esperada))
    return dcg / idcg if idcg else 1.0


def avaliar(modo: str, scorer: Scorer | None = None, verbose: bool = True) -> dict:
    gab = json.loads((RAIZ / "eval" / "gabarito.json").read_text(encoding="utf-8"))
    scorer = scorer or get_scorer()
    scorer.referencia = date.fromisoformat(gab["data_referencia"])
    edital, candidatos = carregar(modo)

    acertos = total = motivos_ok = motivos_total = 0
    ndcgs, erros = [], []
    for cargo, esperado in gab["cargos"].items():
        perfil = next((p for p in edital.perfis if p.cargo == cargo), None)
        if perfil is None:
            erros.append(f"[{cargo}] cargo não encontrado na extração do edital")
            continue
        rk = scorer.ranking(perfil, candidatos)
        aptos = [r.candidato for r in rk.resultados if r.elegivel]
        ndcgs.append(ndcg(aptos, esperado["aptos_em_ordem"]))
        for r in rk.resultados:
            deveria = r.candidato in esperado["aptos_em_ordem"]
            total += 1
            if r.elegivel == deveria:
                acertos += 1
            else:
                erros.append(f"[{cargo}] {r.candidato}: esperado {'apto' if deveria else 'inapto'}, obtido "
                             f"{'apto' if r.elegivel else 'inapto'} (score {r.score})")
            if not deveria:
                motivos = sorted({c.tipo for c in r.criterios if c.obrigatorio and c.status != StatusCriterio.atende})
                motivos_total += 1
                if motivos == sorted(esperado["inaptos"][r.candidato]):
                    motivos_ok += 1
                else:
                    erros.append(f"[{cargo}] {r.candidato}: motivos {motivos}, esperado {sorted(esperado['inaptos'][r.candidato])}")
        if verbose:
            print(f"\n{cargo}")
            for i, r in enumerate(rk.resultados, 1):
                print(f"  {i}. {r.candidato:<26} {'APTO  ' if r.elegivel else 'inapto'} {r.score:5.1f}")

    m = {
        "modo": modo,
        "acuracia_apto_inapto": round(acertos / total, 3) if total else 0.0,
        "acuracia_motivos_inaptidao": round(motivos_ok / motivos_total, 3) if motivos_total else 0.0,
        "ndcg_ordem_aptos": round(sum(ndcgs) / len(ndcgs), 3) if ndcgs else 0.0,
        "decisoes_avaliadas": total,
        "erros": erros,
    }
    if verbose:
        print("\nResultado")
        for k in ("acuracia_apto_inapto", "acuracia_motivos_inaptidao", "ndcg_ordem_aptos", "decisoes_avaliadas"):
            print(f"  {k}: {m[k]}")
        for e in erros:
            print(f"  ! {e}")
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["gabarito", "llm"], default="gabarito")
    args = ap.parse_args()
    if args.modo == "llm" and get_settings().llm_provider == "demo":
        raise SystemExit("Defina LLM_PROVIDER e LLM_API_KEY para o modo llm.")
    avaliar(args.modo)
