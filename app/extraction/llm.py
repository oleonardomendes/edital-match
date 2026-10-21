"""Clientes de LLM que devolvem objetos Pydantic validados.

Todos seguem a mesma interface: ``extrair(prompt, texto, schema) -> schema``.
"""

from __future__ import annotations

import json
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class ErroExtracao(RuntimeError):
    pass


class LLM(Protocol):
    def extrair(self, instrucoes: str, texto: str, schema: type[T]) -> T: ...


class AnthropicLLM:
    """Usa tool use para obrigar o modelo a responder no formato do schema."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model

    def extrair(self, instrucoes: str, texto: str, schema: type[T]) -> T:
        tool = {
            "name": "registrar",
            "description": "Registra os dados extraídos do documento.",
            "input_schema": schema.model_json_schema(),
        }
        for tentativa in range(2):
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=8000,
                temperature=0,
                system=instrucoes,
                tools=[tool],
                tool_choice={"type": "tool", "name": "registrar"},
                messages=[{"role": "user", "content": f"<documento>\n{texto}\n</documento>"}],
            )
            bloco = next((b for b in resp.content if b.type == "tool_use"), None)
            if bloco is None:
                continue
            try:
                return schema.model_validate(bloco.input)
            except ValidationError as exc:
                if tentativa == 1:
                    raise ErroExtracao(f"Resposta fora do formato esperado: {exc}") from exc
        raise ErroExtracao("O modelo não devolveu dados estruturados.")


class OpenAICompatibleLLM:
    """OpenAI, Groq ou qualquer API compatível com chat completions."""

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def extrair(self, instrucoes: str, texto: str, schema: type[T]) -> T:
        sistema = (
            f"{instrucoes}\n\nResponda somente com um JSON válido que siga este JSON Schema:\n"
            f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
        )
        mensagens = [
            {"role": "system", "content": sistema},
            {"role": "user", "content": f"<documento>\n{texto}\n</documento>"},
        ]
        for tentativa in range(2):
            resp = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=mensagens,
            )
            conteudo = resp.choices[0].message.content or ""
            try:
                return schema.model_validate_json(conteudo)
            except ValidationError as exc:
                if tentativa == 1:
                    raise ErroExtracao(f"Resposta fora do formato esperado: {exc}") from exc
                mensagens += [
                    {"role": "assistant", "content": conteudo},
                    {"role": "user", "content": f"O JSON não seguiu o schema. Erros: {exc}. Corrija e responda só o JSON."},
                ]
        raise ErroExtracao("O modelo não devolveu dados estruturados.")


class SemLLM:
    """Modo demo: só funciona para documentos que já estão no cache de extração."""

    def extrair(self, instrucoes: str, texto: str, schema: type[T]) -> T:
        raise ErroExtracao(
            "Modo demo: este documento não está entre os exemplos. Configure LLM_PROVIDER e LLM_API_KEY para analisar novos arquivos."
        )


def criar_llm(provider: str, model: str, api_key: str | None, base_url: str | None) -> LLM:
    if provider == "anthropic":
        return AnthropicLLM(model, api_key)
    if provider == "openai":
        return OpenAICompatibleLLM(model, api_key, base_url)
    if provider == "demo":
        return SemLLM()
    raise ValueError(f"LLM_PROVIDER desconhecido: {provider}")
