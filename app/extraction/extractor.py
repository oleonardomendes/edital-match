"""Transforma texto de documento em dados estruturados, com cache por conteúdo.

O cache usa o hash do texto: o mesmo arquivo enviado de novo não gera outra
chamada ao LLM. Ele também alimenta o modo demo com os documentos de exemplo.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

from app.extraction.llm import LLM
from app.extraction.prompts import PROMPT_CARGOS, PROMPT_CV, PROMPT_EDITAL, PROMPT_PERFIL
from app.extraction.secoes import selecionar_trechos
from app.schemas import ListaCargos, PerfilCandidato, PerfilEdital, RequisitosEdital


class Cache(Protocol):
    def get(self, chave: str) -> str | None: ...
    def set(self, chave: str, tipo: str, valor: str) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get(self, chave: str) -> str | None:
        return self._d.get(chave)

    def set(self, chave: str, tipo: str, valor: str) -> None:
        self._d[chave] = valor


def chave_texto(tipo: str, texto: str) -> str:
    return f"{tipo}:" + hashlib.sha256(" ".join(texto.split()).encode()).hexdigest()


class Extractor:
    def __init__(self, llm: LLM, cache: Cache, limite_edital: int = 40_000) -> None:
        self.llm = llm
        self.cache = cache
        self.limite_edital = limite_edital

    def edital(self, texto: str, contexto: str | None = None) -> RequisitosEdital:
        """Extrai os requisitos do edital.

        ``contexto`` são os trechos recuperados pelo RAG (com página). Sem ele,
        usa a seleção por palavras-chave, que não precisa de banco.
        """
        enviar = contexto or selecionar_trechos(texto.replace("\f", "\n"), limite=self.limite_edital)
        return self._extrair("edital", texto, PROMPT_EDITAL, RequisitosEdital, enviar=enviar)

    def cargos(self, texto: str, contexto: str) -> ListaCargos:
        """Etapa 1 em editais longos: a lista de perfis e as regras da equipe."""
        return self._extrair("cargos", texto, PROMPT_CARGOS, ListaCargos, enviar=contexto)

    def perfil(self, texto: str, cargo: str, contexto: str) -> PerfilEdital:
        """Etapa 2: os requisitos de um perfil, a partir dos trechos recuperados para ele."""
        prompt = PROMPT_PERFIL.replace("{cargo}", cargo)
        return self._extrair(f"perfil:{cargo}", texto, prompt, PerfilEdital, enviar=contexto)

    def candidato(self, texto: str) -> PerfilCandidato:
        return self._extrair("cv", texto, PROMPT_CV, PerfilCandidato)

    def _extrair(self, tipo, texto, prompt, schema, enviar: str | None = None):
        chave = chave_texto(tipo, texto)
        if (salvo := self.cache.get(chave)) is not None:
            return schema.model_validate_json(salvo)
        resultado = self.llm.extrair(prompt, enviar or texto, schema)
        self.cache.set(chave, tipo, resultado.model_dump_json())
        return resultado
