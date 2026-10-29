"""Monta o contexto que vai para o LLM na extração de requisitos.

Um edital completo com anexos passa fácil de 100 páginas, e a maior parte
(minuta de contrato, sanções, modelos de declaração) não fala da equipe.
Em vez de mandar o documento inteiro, o sistema faz várias perguntas fixas ao
índice e envia só os trechos recuperados, com a página de cada um.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import TrechoEdital

from app.matching.embeddings import Embedder
from app.rag.busca import Resultado, buscar, formatar_contexto

CONSULTAS_EXTRACAO = [
    "objeto da contratação",
    "equipe técnica mínima e perfis profissionais exigidos",
    "qualificação técnico-profissional e atestado de responsabilidade técnica",
    "formação acadêmica exigida graduação diploma curso superior",
    "experiência profissional mínima em anos comprovada",
    "certificações exigidas certificado oficial",
    "conhecimentos técnicos ferramentas linguagens tecnologias exigidas",
    "critérios de pontuação da proposta técnica pontos por profissional",
    "comprovação da equipe na assinatura do contrato ou substituição de profissional",
]


CONSULTAS_CARGOS = [
    "objeto da contratação",
    "equipe técnica mínima e perfis profissionais exigidos",
    "quadro de profissionais perfil quantidade",
    "composição mínima do time perfis profissionais",
    "relação de perfis profissionais valor salarial",
    "requisitos de formação da equipe técnicos capacitados",
    "comprovação da experiência e qualificação dos profissionais após a assinatura do contrato",
    "substituição de profissional por outro de experiência equivalente",
]


def primeiras_colunas(session: Session, edital_id: int, limite: int = 2_500) -> str:
    """Primeira célula de cada linha das tabelas do edital, com a página.

    Os perfis da equipe quase sempre aparecem como linhas de uma tabela
    ("Arquiteto Pleno | formação | experiência | ..."). A busca por similaridade
    acha alguns trechos dessa tabela, mas não todos. Esta lista curta, tirada da
    estrutura do documento, dá ao LLM a visão do quadro inteiro.
    """
    linhas = session.scalars(
        select(TrechoEdital).where(TrechoEdital.edital_id == edital_id, TrechoEdital.texto.contains(" | ")).order_by(TrechoEdital.ordem)
    )
    vistos, saida, tamanho = set(), [], 0
    for t in linhas:
        for linha in t.texto.splitlines():
            celulas = [c.strip() for c in linha.split(" | ")]
            if len(celulas) < 3 or not 4 <= len(celulas[0]) <= 80:
                continue
            chave = celulas[0].lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            item = f"- {celulas[0]} (p. {t.pagina})"
            if tamanho + len(item) > limite:
                break
            saida.append(item)
            tamanho += len(item) + 1
    return "\n".join(saida)


def contexto_dos_cargos(session: Session, edital_id: int, embedder: Embedder, limite: int) -> str:
    """Contexto da etapa 1: trechos recuperados mais a primeira coluna das tabelas."""
    tabelas = primeiras_colunas(session, edital_id, limite=min(2_500, limite // 3))
    texto, _ = montar_contexto(session, edital_id, embedder, limite - len(tabelas), consultas=CONSULTAS_CARGOS, vizinhos=True)
    if tabelas:
        texto += "\n\n[Tabelas do edital: primeira coluna de cada linha]\n" + tabelas
    return texto


def contexto_do_cargo(session: Session, edital_id: int, cargo: str, embedder: Embedder, limite: int) -> str:
    """Trechos que descrevem um perfil específico (formação, experiência, conhecimentos)."""
    consultas = [cargo, f"{cargo} formação curso superior experiência mínima anos", f"{cargo} conhecimentos certificação"]
    return montar_contexto(session, edital_id, embedder, limite, k=4, consultas=consultas, vizinhos=True)[0]


def montar_contexto(session: Session, edital_id: int, embedder: Embedder, limite: int, k: int = 5,
                    consultas: list[str] | None = None, vizinhos: bool = False) -> tuple[str, list[Resultado]]:
    """Junta os melhores trechos de cada consulta até o limite de caracteres.

    Os trechos entram por ordem de relevância (o melhor de cada consulta
    primeiro), mas saem na ordem em que aparecem no edital, para o LLM ler um
    texto contínuo.
    """
    por_consulta = [buscar(session, edital_id, c, embedder, k=k) for c in (consultas or CONSULTAS_EXTRACAO)]
    escolhidos: dict[int, Resultado] = {}
    tamanho = 0
    for posicao in range(k):  # rodadas: 1º de cada consulta, depois o 2º de cada, ...
        for resultados in por_consulta:
            if posicao >= len(resultados) or resultados[posicao].id in escolhidos:
                continue
            r = resultados[posicao]
            custo = len(r.texto) + len(r.secao) + 20
            if tamanho + custo > limite:
                continue
            escolhidos[r.id] = r
            tamanho += custo
    # Leva também o trecho seguinte dos melhores: tabelas e listas costumam continuar logo abaixo.
    if vizinhos:
        for r in sorted(escolhidos.values(), key=lambda r: -r.score):
            prox = session.scalar(select(TrechoEdital).where(TrechoEdital.edital_id == edital_id, TrechoEdital.ordem == r.ordem + 1))
            if prox is None or prox.id in escolhidos:
                continue
            custo = len(prox.texto) + len(prox.secao) + 20
            if tamanho + custo > limite:
                break
            escolhidos[prox.id] = Resultado(prox.id, prox.ordem, prox.pagina, prox.secao, prox.texto, 0.0, ["vizinho"])
            tamanho += custo
    lista = list(escolhidos.values())
    return formatar_contexto(lista), lista
