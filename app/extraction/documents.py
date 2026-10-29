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


def parece_tabela(texto: str) -> bool:
    """Página com muitas linhas curtas costuma ser tabela: o pypdf quebra cada célula em pedaços.

    É uma checagem barata, para só essas páginas passarem pelo pdfplumber (mais lento).
    """
    linhas = [l for l in texto.splitlines() if l.strip()]
    if len(linhas) < 15:
        return False
    curtas = sum(1 for l in linhas if len(l.strip()) <= 30)
    return curtas / len(linhas) >= 0.45


def remover_repetidas(paginas: list[str], fracao: float = 0.6) -> list[str]:
    """Tira cabeçalhos e rodapés que se repetem na maioria das páginas.

    Em editais, linhas como "Termo de Referência 10/2023 · UASG 201057" aparecem
    em todas as páginas e poluem os trechos e a busca.
    """
    if len(paginas) < 5:
        return paginas
    from collections import Counter

    chave = lambda l: re.sub(r"\d+", "#", " ".join(l.split()).lower())
    contagem = Counter(k for p in paginas for k in {chave(l) for l in p.splitlines() if l.strip()})
    repetidas = {k for k, n in contagem.items() if n >= fracao * len(paginas)}
    return ["\n".join(l for l in p.splitlines() if chave(l) not in repetidas) for p in paginas]


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
        paginas = [page.extract_text() or "" for page in reader.pages]
        suspeitas = [i for i, t in enumerate(paginas) if parece_tabela(t)]
    except Exception as exc:  # pypdf lança vários tipos
        raise DocumentoInvalido("PDF corrompido ou protegido por senha.") from exc
    if suspeitas:
        try:
            for n, texto in paginas_com_tabela(conteudo, suspeitas).items():
                paginas[n] = texto
        except Exception:  # se o pdfplumber falhar, fica a leitura comum
            pass
    return remover_repetidas(paginas)


def _docx(conteudo: bytes) -> str:
    doc = Document(io.BytesIO(conteudo))
    partes = [p.text for p in doc.paragraphs]
    for tabela in doc.tables:
        for linha in tabela.rows:
            partes.append(" | ".join(c.text for c in linha.cells))
    return "\n".join(partes)
