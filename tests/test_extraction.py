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
