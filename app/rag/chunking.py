"""Divide o edital em trechos para indexação, guardando página e seção.

Cada trecho leva o título da seção em que está (ex.: "8.2 QUALIFICAÇÃO TÉCNICA").
Um parágrafo solto como "experiência mínima de 3 anos" quase não diz nada;
com o título da seção na frente, a busca sabe de que perfil e de que parte do
edital ele fala.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "8.2. QUALIFICAÇÃO TÉCNICA", "CLÁUSULA DÉCIMA – DAS PENALIDADES", "ANEXO I - TERMO DE REFERÊNCIA"
_NUMERADO = re.compile(r"^\s*\d{1,2}(\.\d{1,2}){0,3}\.?\s+[A-ZÀ-Ú][^\n]{2,100}$")
_PALAVRA_CHAVE = re.compile(r"^\s*(CL[ÁA]USULA|ANEXO|CAP[ÍI]TULO|SE[ÇC][ÃA]O|T[ÍI]TULO)\b", re.I)


@dataclass
class Trecho:
    ordem: int
    pagina: int
    secao: str
    texto: str

    @property
    def texto_indexado(self) -> str:
        return f"{self.secao}\n{self.texto}" if self.secao else self.texto


def eh_titulo(linha: str) -> bool:
    linha = linha.strip()
    if not 4 <= len(linha) <= 110 or linha.endswith((",", ";")) or " | " in linha:
        return False
    letras = [c for c in linha if c.isalpha()]
    if len(letras) < 4:
        return False
    maiusculas = sum(c.isupper() for c in letras) / len(letras)
    if _PALAVRA_CHAVE.match(linha) and maiusculas > 0.5:
        return True
    if _NUMERADO.match(linha) and (maiusculas > 0.6 or len(linha) <= 60):
        return True
    # Linha toda em maiúsculas vira título só se for longa o bastante: "ASP e .NET"
    # numa célula de tabela não é título de seção.
    return maiusculas > 0.85 and len(linha) >= 12 and sum(len(p) >= 3 for p in linha.split()) >= 2


def _partir(linha: str, tamanho: int) -> list[str]:
    """Quebra uma linha muito longa (comum em DOCX e TXT) em frases que caibam no trecho."""
    if len(linha) <= tamanho:
        return [linha]
    pedacos, atual = [], ""
    for frase in re.split(r"(?<=[.;:])\s+", linha):
        while len(frase) > tamanho:
            corte = frase.rfind(" ", 0, tamanho)
            corte = corte if corte > 0 else tamanho
            pedacos.append(frase[:corte])
            frase = frase[corte:].strip()
        if atual and len(atual) + len(frase) + 1 > tamanho:
            pedacos.append(atual)
            atual = frase
        else:
            atual = f"{atual} {frase}".strip()
    if atual:
        pedacos.append(atual)
    return pedacos


def dividir(paginas: list[str], tamanho: int = 1_200, sobra: int = 200) -> list[Trecho]:
    """Agrupa linhas em trechos de até ``tamanho`` caracteres.

    Um título novo fecha o trecho atual, para que um trecho não misture duas
    seções. Os últimos ``sobra`` caracteres passam para o trecho seguinte, para
    uma frase cortada no meio aparecer inteira em pelo menos um deles.
    """
    trechos: list[Trecho] = []
    secao, atual, pagina_inicio = "", [], 1

    def fechar(pagina_atual: int, manter_sobra: bool) -> None:
        nonlocal atual, pagina_inicio
        texto = "\n".join(atual).strip()
        if len(texto) >= 40:
            trechos.append(Trecho(len(trechos), pagina_inicio, secao, texto))
        resto = texto[-sobra:] if manter_sobra and len(texto) > sobra else ""
        atual = [resto[resto.find(" ") + 1 :]] if resto else []
        pagina_inicio = pagina_atual

    for numero, pagina in enumerate(paginas, start=1):
        # Texto corrido pode continuar na página seguinte (uma frase cortada pela
        # quebra de página fica inteira). Página de tabela sempre começa trecho novo,
        # para cada linha da tabela levar a página certa.
        if any(x.strip() for x in atual) and " | " in pagina:
            fechar(numero, manter_sobra=False)
        if not any(x.strip() for x in atual):
            pagina_inicio = numero
        for linha in pagina.splitlines():
            linha = " ".join(linha.split())
            if not linha:
                continue
            if eh_titulo(linha):
                if sum(len(x) for x in atual) > 0:
                    fechar(numero, manter_sobra=False)
                secao, pagina_inicio = linha[:200], numero
                continue
            for parte in _partir(linha, tamanho - sobra):
                if sum(len(x) + 1 for x in atual) + len(parte) > tamanho and atual:
                    fechar(numero, manter_sobra=True)
                atual.append(parte)
    fechar(len(paginas), manter_sobra=False)
    return trechos
