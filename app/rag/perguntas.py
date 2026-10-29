"""Perguntas em linguagem natural sobre o edital, respondidas com citação de página."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.extraction.llm import LLM, ErroExtracao
from app.matching.embeddings import Embedder
from app.rag.busca import Resultado, buscar, formatar_contexto

PROMPT_PERGUNTA = """Você responde perguntas sobre um edital de licitação usando apenas os trechos fornecidos.

Regras:
- Responda em português, em até 5 frases, de forma direta.
- Use só o que está nos trechos. Se eles não respondem à pergunta, marque encontrou=false
  e diga que o edital, nos trechos encontrados, não trata do assunto. Não use conhecimento
  externo sobre a lei para preencher lacunas.
- Em paginas, liste as páginas (o número em [p. N]) dos trechos que sustentam a resposta.
"""


class RespostaEdital(BaseModel):
    encontrou: bool = Field(description="Falso quando os trechos não respondem à pergunta")
    resposta: str
    paginas: list[int] = Field(default_factory=list)


def perguntar(session: Session, edital_id: int, pergunta: str, embedder: Embedder, llm: LLM, k: int = 6) -> tuple[RespostaEdital | None, list[Resultado], str | None]:
    """Recupera os trechos e pede a resposta ao LLM.

    Sem LLM configurado (modo demo), devolve só os trechos encontrados, para
    mostrar a etapa de busca funcionando.
    """
    trechos = buscar(session, edital_id, pergunta, embedder, k=k)
    if not trechos:
        return RespostaEdital(encontrou=False, resposta="Nenhum trecho do edital corresponde à pergunta."), [], None
    contexto = formatar_contexto(trechos)
    try:
        resposta = llm.extrair(PROMPT_PERGUNTA, f"Pergunta: {pergunta}\n\nTrechos do edital:\n{contexto}", RespostaEdital)
    except ErroExtracao as exc:
        return None, trechos, str(exc)
    validas = {t.pagina for t in trechos}
    resposta.paginas = sorted(p for p in set(resposta.paginas) if p in validas)
    return resposta, trechos, None
