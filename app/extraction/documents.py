"""Leitura de texto de PDF, DOCX e TXT."""

from __future__ import annotations

import io

from docx import Document
from pypdf import PdfReader


class DocumentoInvalido(ValueError):
    pass


def extrair_paginas(nome_arquivo: str, conteudo: bytes) -> list[str]:
    """Texto do documento separado por página. DOCX e TXT viram uma página só."""
    nome = nome_arquivo.lower()
    if nome.endswith(".pdf"):
        paginas = _pdf(conteudo)
    elif nome.endswith(".docx"):
        paginas = [_docx(conteudo)]
    elif nome.endswith((".txt", ".md")):
        paginas = conteudo.decode("utf-8", errors="replace").split("\f")
    else:
        raise DocumentoInvalido(f"Formato não suportado: {nome_arquivo}. Envie PDF, DOCX ou TXT.")
    paginas = [p.strip() for p in paginas]
    if sum(len(p) for p in paginas) < 30:
        raise DocumentoInvalido(
            f"Não foi possível ler texto de {nome_arquivo}. Se for um PDF escaneado, envie uma versão com texto selecionável."
        )
    return paginas


def juntar_paginas(paginas: list[str]) -> str:
    """Guarda a quebra de página como \\f, para o texto poder ser reindexado com o número da página."""
    return "\f".join(paginas)


def extrair_texto(nome_arquivo: str, conteudo: bytes) -> str:
    return juntar_paginas(extrair_paginas(nome_arquivo, conteudo))


def _pdf(conteudo: bytes) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(conteudo))
        return [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf lança vários tipos
        raise DocumentoInvalido("PDF corrompido ou protegido por senha.") from exc


def _docx(conteudo: bytes) -> str:
    doc = Document(io.BytesIO(conteudo))
    partes = [p.text for p in doc.paragraphs]
    for tabela in doc.tables:
        for linha in tabela.rows:
            partes.append(" | ".join(c.text for c in linha.cells))
    return "\n".join(partes)
