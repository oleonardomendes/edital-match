"""Leitura de texto de PDF, DOCX e TXT."""

from __future__ import annotations

import io

from docx import Document
from pypdf import PdfReader


class DocumentoInvalido(ValueError):
    pass


def extrair_texto(nome_arquivo: str, conteudo: bytes) -> str:
    nome = nome_arquivo.lower()
    if nome.endswith(".pdf"):
        texto = _pdf(conteudo)
    elif nome.endswith(".docx"):
        texto = _docx(conteudo)
    elif nome.endswith((".txt", ".md")):
        texto = conteudo.decode("utf-8", errors="replace")
    else:
        raise DocumentoInvalido(f"Formato não suportado: {nome_arquivo}. Envie PDF, DOCX ou TXT.")
    texto = texto.strip()
    if len(texto) < 30:
        raise DocumentoInvalido(
            f"Não foi possível ler texto de {nome_arquivo}. Se for um PDF escaneado, envie uma versão com texto selecionável."
        )
    return texto


def _pdf(conteudo: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(conteudo))
    except Exception as exc:  # pypdf lança vários tipos
        raise DocumentoInvalido("PDF corrompido ou protegido por senha.") from exc
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _docx(conteudo: bytes) -> str:
    doc = Document(io.BytesIO(conteudo))
    partes = [p.text for p in doc.paragraphs]
    for tabela in doc.tables:
        for linha in tabela.rows:
            partes.append(" | ".join(c.text for c in linha.cells))
    return "\n".join(partes)
