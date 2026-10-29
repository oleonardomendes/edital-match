from pathlib import Path

import pytest

from app.extraction.documents import DocumentoInvalido, extrair_texto
from app.extraction.extractor import Extractor, MemoryCache
from app.schemas import PerfilCandidato

PDFS = Path(__file__).resolve().parent.parent / "samples" / "pdfs"


class LLMFalso:
    def __init__(self):
        self.chamadas = 0

    def extrair(self, instrucoes, texto, schema):
        self.chamadas += 1
        return schema(nome="Fulana de Tal")


def test_cache_evita_segunda_chamada_ao_llm():
    llm = LLMFalso()
    ext = Extractor(llm, MemoryCache())
    texto = "Fulana de Tal. Desenvolvedora Python desde 2020."
    a = ext.candidato(texto)
    b = ext.candidato(texto + "  \n")  # espaços extras não mudam o hash
    assert isinstance(a, PerfilCandidato) and a == b
    assert llm.chamadas == 1


def test_le_texto_do_pdf():
    texto = extrair_texto("cv.pdf", (PDFS / "cv_bruno_sales.pdf").read_bytes())
    assert "Bruno Henrique Sales" in texto and "PL/SQL" in texto


def test_pdf_sem_texto_gera_erro_claro():
    with pytest.raises(DocumentoInvalido, match="escaneado"):
        extrair_texto("vazio.txt", b"   ")


def test_limite_do_edital_reduz_o_texto_enviado():
    from app.extraction.extractor import Extractor, MemoryCache
    from app.schemas import RequisitosEdital

    enviados = []

    class LLMEspiao:
        def extrair(self, instrucoes, texto, schema):
            enviados.append(texto)
            return RequisitosEdital(perfis=[])

    texto = ("Cláusula genérica sem interesse. " * 2000) + "Perfil: Analista com experiência mínima de 3 anos."
    Extractor(LLMEspiao(), MemoryCache(), limite_edital=6000).edital(texto)
    assert len(enviados[0]) <= 6500


def test_erro_de_limite_do_provedor_vira_mensagem_clara():
    from types import SimpleNamespace

    import httpx
    from openai import APIStatusError

    from app.extraction.llm import MSG_LIMITE, ErroExtracao, OpenAICompatibleLLM
    from app.schemas import RequisitosEdital

    llm = OpenAICompatibleLLM.__new__(OpenAICompatibleLLM)
    llm._model, llm.max_saida = "openai/gpt-oss-120b", 100
    resp = httpx.Response(413, request=httpx.Request("POST", "https://x"))

    def falha(**_):
        raise APIStatusError("Request too large", response=resp, body=None)

    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=falha)))
    try:
        llm.extrair("x", "y", RequisitosEdital)
    except ErroExtracao as exc:
        assert str(exc) == MSG_LIMITE
    else:
        raise AssertionError("deveria falhar")


def test_remove_caracteres_de_controle():
    from app.extraction.documents import extrair_paginas

    paginas = extrair_paginas("a.txt", "Edital\x00 com NUL.\fSegunda página".encode())
    assert paginas == ["Edital  com NUL.", "Segunda página"]


def test_tabela_vira_linhas_com_colunas():
    from app.extraction.documents import tabela_em_linhas

    layout = "\n".join([
        "UASG 201057                                   Termo de Referência",
        "  Perfil              Formação                 Conhecimentos",
        "  Analista de         Curso superior           * Java",
        "  Testes Pleno        completo em TI           * Selenium",
        "                      ou Exatas                * REST",
        "  Desenvolvedor       Curso superior           * C#",
        "  Sênior              completo                 * ASP.NET",
        "                      em TI                    * SQL Server",
    ])
    linhas = tabela_em_linhas(layout).splitlines()
    assert linhas[2] == "Analista de | Curso superior | * Java"
    assert tabela_em_linhas("Texto corrido de um parágrafo comum.\n" * 10) is None


def test_pdf_com_tabela_de_bordas_mantem_cada_linha_junta(tmp_path):
    """Tabela de perfis com várias colunas: cada perfil sai numa linha, com todas as células."""
    reportlab = pytest.importorskip("reportlab")  # noqa: F841
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    from app.extraction.documents import extrair_paginas

    st = getSampleStyleSheet()["BodyText"]
    linhas = [[Paragraph(t, st) for t in ("Perfil", "Experiência", "Formação", "Conhecimentos")]]
    for perfil, exp, conh in [("Analista de Testes Pleno - JAVA", "mínima de 3 (três) anos em testes de aplicações web", "* Java * Selenium"),
                              ("Desenvolvedor Sênior - ASP e .NET", "mínima de 5 (cinco) anos em desenvolvimento", "* C# * ASP.NET")] * 3:
        linhas.append([Paragraph(t, st) for t in (perfil, exp, "Curso superior completo em Tecnologia da Informação ou Exatas", conh)])
    tabela = Table(linhas, colWidths=[110, 140, 140, 110])
    tabela.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    arquivo = tmp_path / "tabela.pdf"
    SimpleDocTemplate(str(arquivo), pagesize=A4).build([Paragraph("4.13. Requisitos de Experiência Profissional", st), tabela])

    texto = extrair_paginas("tabela.pdf", arquivo.read_bytes())[0]
    assert texto.startswith("4.13. Requisitos de Experiência Profissional")
    assert "Desenvolvedor Sênior - ASP e .NET | mínima de 5 (cinco) anos em desenvolvimento | Curso superior" in texto
