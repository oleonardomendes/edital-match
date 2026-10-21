"""Garante que o motor continua concordando com o gabarito humano."""

from app.matching.scorer import Scorer
from eval.run_eval import avaliar


def test_motor_concorda_com_gabarito():
    m = avaliar("gabarito", scorer=Scorer(), verbose=False)
    assert m["erros"] == []
    assert m["acuracia_apto_inapto"] == 1.0
    assert m["ndcg_ordem_aptos"] == 1.0
