"""Garante que o motor continua concordando com o gabarito humano."""

from app.matching.scorer import Scorer
from eval.run_eval import avaliar


def test_motor_concorda_com_gabarito():
    m = avaliar("gabarito", scorer=Scorer(), verbose=False)
    assert m["erros"] == []
    assert m["acuracia_apto_inapto"] == 1.0
    assert m["ndcg_ordem_aptos"] == 1.0


def test_modo_llm_com_extracao_perfeita():
    """Um LLM que devolve exatamente o gabarito deve zerar os erros de extração e de decisão."""
    import json
    from pathlib import Path

    from app.extraction.extractor import chave_texto

    cache = json.loads((Path(__file__).resolve().parent.parent / "samples" / "cache_extracoes.json").read_text(encoding="utf-8"))

    class LLMGabarito:
        def extrair(self, instrucoes, texto, schema):
            tipo = "edital" if schema.__name__ == "RequisitosEdital" else "cv"
            return schema.model_validate(cache[chave_texto(tipo, texto)]["valor"])

    m = avaliar("llm", scorer=Scorer(), verbose=False, llm=LLMGabarito())
    assert m["erros"] == []
    ed = m["extracao"]["edital"]
    assert ed["requisitos_encontrados"] == ed["requisitos_esperados"] == ed["obrigatoriedade_correta"]
    assert ed["faltando"] == [] and ed["requisitos_a_mais"] == 0
    cv = m["extracao"]["curriculos"]
    assert cv["nomes_corretos"] == cv["total"] == 8 and cv["maior_diferenca_em_anos"] == 0
