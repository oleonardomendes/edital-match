"""Localiza, em editais longos, os trechos que falam da equipe técnica.

Editais completos passam de 100 páginas, e a maior parte (minuta de contrato,
modelos de declaração, sanções) não interessa para a equipe. Mandar tudo ao
LLM custa mais e aumenta a chance de erro. Esta etapa recupera só os trechos
relevantes antes da extração: é um RAG simples, por palavras-chave, que não
depende de modelo de embeddings e explica por que escolheu cada trecho.
"""

from __future__ import annotations

import re

from app.matching.text import normalizar

# Termos típicos da seção de equipe técnica em termos de referência.
TERMOS = {
    "equipe tecnica": 4, "perfil profissional": 4, "perfis profissionais": 4, "qualificacao tecnica": 3,
    "profissional": 1, "profissionais": 1, "formacao": 2, "diploma": 2, "graduacao": 2,
    "experiencia minima": 3, "experiencia": 1, "anos": 1, "certificacao": 2, "certificado": 1,
    "curriculo": 2, "exigido": 1, "desejavel": 2, "pontuacao": 1, "conhecimento em": 2,
}


def _janelas(texto: str, tamanho: int, sobra: int) -> list[tuple[int, str]]:
    passo, janelas, i = tamanho - sobra, [], 0
    while i < len(texto):
        janelas.append((i, texto[i : i + tamanho]))
        i += passo
    return janelas


def _relevancia(trecho: str) -> int:
    t = f" {normalizar(trecho)} "
    return sum(peso * len(re.findall(rf"(?<![a-z]){re.escape(termo)}", t)) for termo, peso in TERMOS.items())


def selecionar_trechos(texto: str, limite: int = 40_000, tamanho: int = 3_000, sobra: int = 300) -> str:
    """Devolve o texto inteiro se couber no limite; senão, o cabeçalho e os trechos mais relevantes, em ordem."""
    if len(texto) <= limite:
        return texto
    cabecalho = texto[:2_000]
    janelas = _janelas(texto[2_000:], tamanho, sobra)
    ranking = sorted(range(len(janelas)), key=lambda k: _relevancia(janelas[k][1]), reverse=True)

    escolhidas: set[int] = set()
    orcamento = limite - len(cabecalho)
    for k in ranking:
        if _relevancia(janelas[k][1]) == 0 or orcamento < tamanho:
            break
        # Leva também a janela seguinte: requisitos costumam continuar no trecho de baixo.
        for vizinha in (k, k + 1):
            if 0 <= vizinha < len(janelas) and vizinha not in escolhidas and orcamento >= tamanho:
                escolhidas.add(vizinha)
                orcamento -= tamanho
    partes = [janelas[k][1] for k in sorted(escolhidas)]
    return cabecalho + "\n\n[...]\n\n" + "\n\n[...]\n\n".join(partes)
