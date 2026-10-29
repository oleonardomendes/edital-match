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


MSG_USO = "O provedor de IA atingiu o limite de uso por minuto do plano. Tente de novo em instantes."
MSG_LIMITE = (
    "O documento passou do limite de tamanho do provedor de IA. Envie só o termo de referência "
    "(a parte com a equipe técnica) ou use um plano com limite maior."
)


def _schema_compacto(schema) -> str:
    """JSON Schema sem títulos e sem espaços: o mesmo contrato com menos tokens."""
    def limpar(no):
        if isinstance(no, dict):
            return {k: limpar(v) for k, v in no.items() if k != "title"}
        if isinstance(no, list):
            return [limpar(v) for v in no]
        return no
    return json.dumps(limpar(schema.model_json_schema()), ensure_ascii=False, separators=(",", ":"))


class LLM(Protocol):
    def extrair(self, instrucoes: str, texto: str, schema: type[T]) -> T: ...


class AnthropicLLM:
    """Usa tool use para obrigar o modelo a responder no formato do schema."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key, max_retries=4, timeout=120)
        self._model = model

    def extrair(self, instrucoes: str, texto: str, schema: type[T]) -> T:
        from anthropic import APIStatusError

        tool = {
            "name": "registrar",
            "description": "Registra os dados extraídos do documento.",
            "input_schema": schema.model_json_schema(),
        }
        for tentativa in range(2):
            try:
                resp = self._client.messages.create(
                    model=self._model,
                    max_tokens=8000,
                    temperature=0,
                    system=instrucoes,
                    tools=[tool],
                    tool_choice={"type": "tool", "name": "registrar"},
                    messages=[{"role": "user", "content": f"<documento>\n{texto}\n</documento>"}],
                )
            except APIStatusError as exc:
                if exc.status_code == 429:
                    raise ErroExtracao(MSG_USO) from exc
                if exc.status_code == 413:
                    raise ErroExtracao(MSG_LIMITE) from exc
                raise ErroExtracao(f"O provedor de IA respondeu com erro {exc.status_code}.") from exc
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

        # O plano gratuito do Groq limita tokens por minuto; o SDK espera e tenta de novo.
        self._client = OpenAI(api_key=api_key, base_url=base_url, max_retries=6, timeout=120)
        self._model = model
        self.max_saida = 4000

    def extrair(self, instrucoes: str, texto: str, schema: type[T]) -> T:
        sistema = (
            f"{instrucoes}\n\nResponda somente com um JSON válido que siga este JSON Schema:\n"
            f"{_schema_compacto(schema)}"
        )
        mensagens = [
            {"role": "system", "content": sistema},
            {"role": "user", "content": f"<documento>\n{texto}\n</documento>"},
        ]
        from openai import APIStatusError

        extra = {"reasoning_effort": "low"} if "gpt-oss" in self._model else {}
        for tentativa in range(2):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    temperature=0,
                    max_tokens=self.max_saida,
                    response_format={"type": "json_object"},
                    messages=mensagens,
                    extra_body=extra or None,
                )
            except APIStatusError as exc:
                if exc.status_code == 429:
                    raise ErroExtracao(MSG_USO) from exc
                if exc.status_code == 413:
                    raise ErroExtracao(MSG_LIMITE) from exc
                raise ErroExtracao(f"O provedor de IA respondeu com erro {exc.status_code}.") from exc
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
