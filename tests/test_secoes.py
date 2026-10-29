from app.extraction.secoes import selecionar_trechos

EQUIPE = (
    "2. EQUIPE TÉCNICA MÍNIMA\n2.1 GERENTE DE PROJETOS: diploma de graduação em TI. Exigido. "
    "Experiência mínima de 5 anos em gestão de projetos. Certificação PMP. Exigido. "
    "Certificação PSM. Desejável, vale 2 pontos."
)


def test_texto_curto_vai_inteiro():
    assert selecionar_trechos("Edital curto. " + EQUIPE) == "Edital curto. " + EQUIPE


def test_edital_longo_mantem_a_secao_da_equipe_e_respeita_o_limite():
    enchimento = "Cláusula de penalidades e sanções administrativas aplicáveis ao contrato. " * 800
    texto = "PREFEITURA DE TESTE - PREGÃO 1/2026\n" + enchimento + EQUIPE + enchimento
    assert len(texto) > 100_000
    sel = selecionar_trechos(texto, limite=20_000)
    assert len(sel) <= 20_000 + 200
    assert "PREFEITURA DE TESTE" in sel
    assert "Experiência mínima de 5 anos" in sel and "Certificação PMP" in sel
