"""Cliente da API pública do PNCP (Portal Nacional de Contratações Públicas).

Usa dois serviços abertos, sem autenticação:

* busca textual de editais: ``/api/search/``;
* arquivos de uma contratação: ``/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos``.

Os arquivos podem ser PDF, DOCX ou um ZIP com vários documentos.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

import httpx

BASE = "https://pncp.gov.br"
FORMATOS = (".pdf", ".docx", ".txt")
# Documentos que trazem os requisitos da equipe; os demais (avisos, atas, mapas de preço) ficam de fora.
TIPOS_UTEIS = ("edital", "termo de refer", "projeto basico", "projeto básico", "estudo tecnico", "anexo")


class ErroPNCP(RuntimeError):
    pass


@dataclass
class Contratacao:
    titulo: str
    descricao: str
    orgao: str
    municipio: str
    uf: str
    modalidade: str
    fim_propostas: str | None
    valor_estimado: float | None
    cnpj: str
    ano: int
    sequencial: int

    @property
    def link(self) -> str:
        return f"{BASE}/app/editais/{self.cnpj}/{self.ano}/{self.sequencial}"


def _cliente(client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "edital-match/0.2"})


def buscar(q: str, pagina: int = 1, abertas: bool = True, client: httpx.Client | None = None) -> list[Contratacao]:
    params = {"q": q, "tipos_documento": "edital", "ordenacao": "-data", "pagina": pagina, "tam_pagina": 10}
    if abertas:
        params["status"] = "recebendo_proposta"
    c = _cliente(client)
    try:
        r = c.get(f"{BASE}/api/search/", params=params)
    except httpx.HTTPError as exc:
        raise ErroPNCP("Não foi possível falar com o PNCP agora. Tente de novo em instantes.") from exc
    if r.status_code == 429:
        raise ErroPNCP("O PNCP limitou o número de consultas. Espere um minuto e tente de novo.")
    if r.status_code != 200:
        raise ErroPNCP(f"O PNCP respondeu com erro {r.status_code}.")
    itens = r.json().get("items", [])
    return [
        Contratacao(
            titulo=i.get("title") or "", descricao=i.get("description") or "", orgao=i.get("orgao_nome") or "",
            municipio=i.get("municipio_nome") or "", uf=i.get("uf") or "", modalidade=i.get("modalidade_licitacao_nome") or "",
            fim_propostas=i.get("data_fim_vigencia"), valor_estimado=i.get("valor_total_estimado"),
            cnpj=i["orgao_cnpj"], ano=int(i["ano"]), sequencial=int(i["numero_sequencial"]),
        )
        for i in itens
        if i.get("orgao_cnpj") and i.get("ano") and i.get("numero_sequencial")
    ]


def _nome_arquivo(resposta: httpx.Response, padrao: str) -> str:
    disp = resposta.headers.get("content-disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disp)
    if m:
        return m.group(1).strip()
    tipo = resposta.headers.get("content-type", "")
    ext = ".pdf" if "pdf" in tipo else ".zip" if "zip" in tipo else ".docx" if "word" in tipo else ""
    return padrao + ext


def _expandir(nome: str, conteudo: bytes) -> list[tuple[str, bytes]]:
    """Abre ZIPs e devolve só os arquivos que o sistema sabe ler."""
    if nome.lower().endswith(".zip") or conteudo[:2] == b"PK" and not nome.lower().endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                return [(n.rsplit("/", 1)[-1], z.read(n)) for n in z.namelist() if n.lower().endswith(FORMATOS)]
        except zipfile.BadZipFile:
            return []
    return [(nome, conteudo)] if nome.lower().endswith(FORMATOS) else []


def baixar_documentos(cnpj: str, ano: int, sequencial: int, limite_mb: int = 30, client: httpx.Client | None = None) -> list[tuple[str, bytes]]:
    """Baixa os documentos úteis de uma contratação (edital, termo de referência e anexos)."""
    if not re.fullmatch(r"\d{14}", cnpj):
        raise ErroPNCP("CNPJ inválido.")
    c = _cliente(client)
    base = f"{BASE}/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos"
    try:
        r = c.get(base)
        if r.status_code == 404:
            raise ErroPNCP("Contratação não encontrada no PNCP.")
        r.raise_for_status()
        arquivos = [a for a in r.json() if a.get("statusAtivo", True)]
        uteis = [a for a in arquivos if any(t in (a.get("tipoDocumentoNome") or a.get("titulo") or "").lower() for t in TIPOS_UTEIS)]
        documentos, total = [], 0
        for a in uteis or arquivos:
            d = c.get(a.get("url") or f"{base}/{a['sequencialDocumento']}")
            d.raise_for_status()
            total += len(d.content)
            if total > limite_mb * 1024 * 1024:
                raise ErroPNCP(f"Os arquivos desta contratação passam de {limite_mb} MB.")
            nome = _nome_arquivo(d, f"{a.get('titulo') or 'documento'}-{a.get('sequencialDocumento', len(documentos) + 1)}")
            documentos.extend(_expandir(nome, d.content))
    except httpx.HTTPError as exc:
        raise ErroPNCP("Falha ao baixar os arquivos do PNCP.") from exc
    if not documentos:
        raise ErroPNCP("A contratação não tem edital em PDF, DOCX ou TXT no PNCP.")
    return documentos
