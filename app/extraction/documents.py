"""Leitura de texto de PDF, DOCX e TXT."""

from __future__ import annotations

import io
import re

from docx import Document
from pypdf import PdfReader


_CONTROLE = re.compile(r"\x00")


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
    # PDFs às vezes trazem o caractere NUL, que o Postgres não aceita em texto.
    paginas = [_CONTROLE.sub(" ", p).strip() for p in paginas]
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


_LACUNA = re.compile(r" {3,}")


def tabela_em_linhas(texto_layout: str) -> str | None:
    """Converte uma página com tabela, extraída no modo layout, em linhas com colunas separadas por " | ".

    Na extração comum, o pypdf lê tabelas de várias colunas fora de ordem e
    mistura as células de linhas diferentes. No modo layout, cada linha do texto
    mantém a posição horizontal das células; trocar os espaços largos por " | "
    deixa o conteúdo de cada linha da tabela junto. Devolve None quando a página
    não parece uma tabela.
    """
    linhas = [l.strip() for l in texto_layout.splitlines() if l.strip()]
    if len(linhas) < 8:
        return None
    com_colunas = sum(1 for l in linhas if _LACUNA.search(l))
    if com_colunas / len(linhas) < 0.4:
        return None
    return "\n".join(_LACUNA.sub(" | ", l) for l in linhas)


def _celula(c: str | None) -> str:
    return " ".join((c or "").split())


def paginas_com_tabela(conteudo: bytes, numeros: list[int]) -> dict[int, str]:
    """Relê com o pdfplumber as páginas que têm tabela.

    O pdfplumber usa as linhas desenhadas da tabela para separar as células, então
    cada linha da tabela vira uma linha de texto ("célula | célula | célula") com o
    conteúdo completo de cada célula, sem misturar linhas diferentes. O texto fora
    das tabelas continua na página, na ordem.
    """
    import pdfplumber

    saida: dict[int, str] = {}
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for n in numeros:
            page = pdf.pages[n]
            tabelas = page.find_tables()
            if not tabelas:
                continue
            caixas = [t.bbox for t in tabelas]

            def fora(obj, caixas=caixas):
                return not any(obj.get("x0", 0) >= x0 - 1 and obj.get("x1", 0) <= x1 + 1 and obj.get("top", 0) >= y0 - 1
                               and obj.get("bottom", 0) <= y1 + 1 for x0, y0, x1, y1 in caixas)

            partes = [page.filter(fora).extract_text() or ""]
            for t in tabelas:
                linhas = [" | ".join(_celula(c) for c in linha) for linha in t.extract() if any(linha)]
                partes.append("\n".join(linhas))
            saida[n] = "\n".join(p for p in partes if p.strip())
    return saida


def _pdf(conteudo: bytes) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(conteudo))
        paginas, suspeitas = [], []
        for i, page in enumerate(reader.pages):
            paginas.append(page.extract_text() or "")
            try:
                if tabela_em_linhas(page.extract_text(extraction_mode="layout") or ""):
                    suspeitas.append(i)
            except Exception:  # o modo layout falha em alguns PDFs; o texto comum continua valendo
                pass
    except Exception as exc:  # pypdf lança vários tipos
        raise DocumentoInvalido("PDF corrompido ou protegido por senha.") from exc
    if suspeitas:
        try:
            for n, texto in paginas_com_tabela(conteudo, suspeitas).items():
                paginas[n] = texto
        except Exception:  # se o pdfplumber falhar, fica a leitura comum
            pass
    return paginas


def _docx(conteudo: bytes) -> str:
    doc = Document(io.BytesIO(conteudo))
    partes = [p.text for p in doc.paragraphs]
    for tabela in doc.tables:
        for linha in tabela.rows:
            partes.append(" | ".join(c.text for c in linha.cells))
    return "\n".join(partes)
