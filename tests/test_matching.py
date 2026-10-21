from datetime import date

import pytest

from app.matching.scorer import Scorer, anos_de_experiencia
from app.matching.similarity import LexicalSimilarity
from app.matching.text import contem_termo, mesmo_item
from app.schemas import (
    Certificacao, Experiencia, Formacao, PerfilCandidato, PerfilEdital, RequisitoCertificacao,
    RequisitoCompetencia, RequisitoExperiencia, RequisitoFormacao, StatusCriterio,
)

REF = date(2026, 10, 1)


@pytest.mark.parametrize("a,b", [
    ("PMP", "PMP - Project Management Professional"),
    ("ITIL Foundation", "ITIL 4 Foundation"),
    ("PostgreSQL", "Postgres"),
    ("Certified ScrumMaster", "CSM"),
    ("Análise e Desenvolvimento de Sistemas", "analise e desenvolvimento de sistemas"),
])
def test_equivalentes(a, b):
    assert mesmo_item(a, b)


@pytest.mark.parametrize("a,b", [
    ("Java", "JavaScript"),
    ("PMP", "CAPM - Certified Associate in Project Management"),
    ("C", "C#"),
    ("Oracle", "MySQL"),
])
def test_nao_equivalentes(a, b):
    assert not mesmo_item(a, b)


def test_contem_termo_respeita_palavra_inteira():
    assert contem_termo("Sistemas em Java com Oracle", "Java")
    assert not contem_termo("Front-end em JavaScript", "Java")


def test_sigla_ti_vale_como_tecnologia_da_informacao():
    sim = LexicalSimilarity()
    assert sim.score("gestão de projetos de tecnologia da informação", "Gerente de Projetos de TI") >= sim.limiar
    assert sim.score("gestão de projetos de tecnologia da informação", "Gerente de Restaurante. Gestão de equipe") < sim.limiar


def _exp(ini, fim, cargo="Dev"):
    return Experiencia(cargo=cargo, inicio=date.fromisoformat(ini), fim=date.fromisoformat(fim) if fim else None)


def test_periodos_simultaneos_contam_uma_vez():
    exps = [_exp("2020-01-01", "2024-01-01"), _exp("2021-01-01", "2023-01-01")]
    assert anos_de_experiencia(exps, REF) == pytest.approx(4.0, abs=0.01)


def test_periodos_separados_somam_e_emprego_atual_vai_ate_a_referencia():
    exps = [_exp("2020-01-01", "2021-01-01"), _exp("2025-10-01", None)]
    assert anos_de_experiencia(exps, REF) == pytest.approx(2.0, abs=0.01)


PERFIL = PerfilEdital(
    cargo="Analista",
    formacao=[RequisitoFormacao(nivel_minimo="graduacao", areas=["Sistemas de Informação"], peso=3)],
    experiencias=[RequisitoExperiencia(area="desenvolvimento de sistemas", anos_minimos=4, peso=3)],
    certificacoes=[RequisitoCertificacao(nome="ITIL Foundation", peso=1)],
    competencias=[RequisitoCompetencia(nome="Oracle", obrigatorio=True, peso=3),
                  RequisitoCompetencia(nome="Jira", alternativas=["MS Project"], peso=1)],
)


def _cand(**kw):
    base = dict(
        nome="Ana",
        formacoes=[Formacao(nivel="graduacao", curso="Sistemas de Informação")],
        experiencias=[Experiencia(cargo="Desenvolvedora", inicio=date(2019, 1, 1), descricao="Desenvolvimento de sistemas com Oracle")],
        certificacoes=[Certificacao(nome="ITIL 4 Foundation")],
        competencias=["MS Project"],
    )
    base.update(kw)
    return PerfilCandidato(**base)


def test_candidato_completo_tem_100_e_eh_elegivel():
    r = Scorer(referencia=REF).avaliar(PERFIL, _cand())
    assert r.elegivel and r.score == 100
    assert all(c.status == StatusCriterio.atende for c in r.criterios)


def test_requisito_obrigatorio_faltando_torna_inelegivel():
    cand = _cand(experiencias=[Experiencia(cargo="Desenvolvedora", inicio=date(2019, 1, 1), descricao="Sistemas em Java")])
    r = Scorer(referencia=REF).avaliar(PERFIL, cand)
    assert not r.elegivel
    oracle = next(c for c in r.criterios if "Oracle" in c.requisito)
    assert oracle.status == StatusCriterio.nao_atende
    assert "Oracle" in r.resumo


def test_graduacao_em_andamento_conta_como_parcial():
    cand = _cand(formacoes=[Formacao(nivel="graduacao", curso="Sistemas de Informação", concluida=False)])
    r = Scorer(referencia=REF).avaliar(PERFIL, cand)
    form = r.criterios[0]
    assert form.status == StatusCriterio.parcial and not r.elegivel


def test_experiencia_insuficiente_pontua_proporcionalmente():
    cand = _cand(experiencias=[Experiencia(cargo="Desenvolvedora", inicio=date(2024, 10, 1), descricao="Desenvolvimento de sistemas com Oracle")])
    exp = Scorer(referencia=REF).avaliar(PERFIL, cand).criterios[1]
    assert exp.status == StatusCriterio.parcial
    assert exp.pontuacao == pytest.approx(0.5, abs=0.01)


def test_desejavel_ausente_reduz_score_mas_nao_elimina():
    r = Scorer(referencia=REF).avaliar(PERFIL, _cand(certificacoes=[]))
    assert r.elegivel and r.score < 100


def test_ranking_coloca_elegiveis_antes_mesmo_com_score_menor():
    forte_inelegivel = _cand(nome="Bia", formacoes=[Formacao(nivel="tecnico", curso="Informática")])
    fraco_elegivel = _cand(nome="Caio", certificacoes=[], competencias=[])
    rk = Scorer(referencia=REF).ranking(PERFIL, [forte_inelegivel, fraco_elegivel])
    assert [r.candidato for r in rk.resultados] == ["Caio", "Bia"]
