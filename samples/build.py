"""Gera os PDFs de exemplo e o cache de extração usado no modo demo.

Uso: python -m samples.build
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.extraction.documents import extrair_texto
from app.extraction.extractor import chave_texto
from samples.candidatos import CANDIDATOS

AQUI = Path(__file__).parent
PDFS = AQUI / "pdfs"
NIVEIS = {
    "medio": "Ensino Médio", "tecnico": "Técnico", "graduacao": "Graduação",
    "pos_graduacao": "Pós-graduação", "mestrado": "Mestrado", "doutorado": "Doutorado",
}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _mes(iso: str | None) -> str:
    if not iso:
        return "atual"
    d = date.fromisoformat(iso)
    return f"{MESES[d.month - 1]}/{d.year}"


def texto_cv(c: dict) -> list[tuple[str, str]]:
    p = c["perfil"]
    linhas: list[tuple[str, str]] = [("titulo", p["nome"]), ("p", c["resumo"]), ("h", "Formação acadêmica")]
    for f in p["formacoes"]:
        fim = f"concluído em {f['ano_conclusao']}" if f["concluida"] else "em andamento"
        linhas.append(("li", f"{NIVEIS[f['nivel']]} em {f['curso']} - {f['instituicao']} ({fim})"))
    linhas.append(("h", "Experiência profissional"))
    for e in p["experiencias"]:
        onde = f" - {e['empresa']}" if e["empresa"] else ""
        linhas.append(("b", f"{e['cargo']}{onde} | {_mes(e['inicio'])} a {_mes(e['fim'])}"))
        linhas.append(("p", e["descricao"]))
        if e["tecnologias"]:
            linhas.append(("p", "Tecnologias: " + ", ".join(e["tecnologias"])))
    if p["certificacoes"]:
        linhas.append(("h", "Certificações"))
        for cert in p["certificacoes"]:
            linhas.append(("li", f"{cert['nome']} - {cert['emissor']} ({cert['ano']})"))
    linhas.append(("h", "Competências"))
    linhas.append(("p", ", ".join(p["competencias"])))
    return linhas


def gerar_pdf(destino: Path, blocos: list[tuple[str, str]]) -> None:
    base = getSampleStyleSheet()
    estilos = {
        "titulo": ParagraphStyle("t", parent=base["Title"], fontSize=16, spaceAfter=6),
        "h": ParagraphStyle("h", parent=base["Heading2"], fontSize=12, spaceBefore=8, spaceAfter=4),
        "b": ParagraphStyle("b", parent=base["Normal"], fontName="Helvetica-Bold", spaceBefore=4),
        "p": ParagraphStyle("p", parent=base["Normal"], leading=14),
        "li": ParagraphStyle("li", parent=base["Normal"], leftIndent=10, leading=14),
    }
    doc = SimpleDocTemplate(str(destino), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title=destino.stem)
    story = []
    for tipo, txt in blocos:
        story.append(Paragraph(("• " if tipo == "li" else "") + txt, estilos[tipo]))
    story.append(Spacer(1, 4))
    doc.build(story)


def blocos_edital(texto: str) -> list[tuple[str, str]]:
    blocos = []
    for linha in texto.strip().splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.isupper() or linha[:2].strip(".").isdigit() and linha.split(" ", 1)[1].isupper():
            blocos.append(("h", linha))
        else:
            blocos.append(("p", linha))
    return blocos


def main() -> None:
    PDFS.mkdir(exist_ok=True)
    cache: dict[str, dict] = {}

    edital_txt = (AQUI / "fontes" / "edital_vale_verde.txt").read_text(encoding="utf-8")
    edital_pdf = PDFS / "edital_vale_verde.pdf"
    gerar_pdf(edital_pdf, blocos_edital(edital_txt))
    gabarito_edital = json.loads((AQUI / "gabarito" / "edital_vale_verde.json").read_text(encoding="utf-8"))
    texto = extrair_texto(edital_pdf.name, edital_pdf.read_bytes())
    cache[chave_texto("edital", texto)] = {"tipo": "edital", "arquivo": edital_pdf.name, "valor": gabarito_edital}

    for c in CANDIDATOS:
        destino = PDFS / c["arquivo"]
        gerar_pdf(destino, texto_cv(c))
        texto = extrair_texto(destino.name, destino.read_bytes())
        cache[chave_texto("cv", texto)] = {"tipo": "cv", "arquivo": destino.name, "valor": c["perfil"]}

    (AQUI / "cache_extracoes.json").write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(cache)} documentos gerados em {PDFS}")


if __name__ == "__main__":
    main()
