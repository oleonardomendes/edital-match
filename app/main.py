from __future__ import annotations

import json
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Candidato, DbCache, Edital, Extracao, criar_tabelas, engine, get_session
from app.extraction.documents import DocumentoInvalido, extrair_texto
from app.extraction.extractor import Extractor
from app.extraction.llm import LLM, ErroExtracao
from app.matching.embeddings import Embedder
from app.matching.scorer import Scorer
from app.schemas import PerfilCandidato, Ranking, RequisitosEdital
from app.services import get_embedder, get_llm, get_scorer, texto_para_busca

RAIZ = Path(__file__).resolve().parent.parent
CACHE_DEMO = RAIZ / "samples" / "cache_extracoes.json"


@asynccontextmanager
async def lifespan(_: FastAPI):
    criar_tabelas()
    carregar_cache_demo()
    yield


app = FastAPI(
    title="Edital Match",
    description="Cruza os requisitos de um edital com currículos e gera um ranking explicável.",
    version="0.1.0",
    lifespan=lifespan,
)


def carregar_cache_demo() -> None:
    """Grava no cache as extrações dos documentos de exemplo, para o modo demo."""
    if not CACHE_DEMO.exists():
        return
    from sqlalchemy.orm import Session as S

    dados = json.loads(CACHE_DEMO.read_text(encoding="utf-8"))
    with S(engine()) as s:
        for chave, item in dados.items():
            if s.get(Extracao, chave) is None:
                s.add(Extracao(chave=chave, tipo=item["tipo"], valor=json.dumps(item["valor"], ensure_ascii=False)))
        s.commit()


def get_extractor(session: Session = Depends(get_session), llm: LLM = Depends(get_llm)) -> Extractor:
    return Extractor(llm, DbCache(session))


async def _ler(arquivo: UploadFile) -> str:
    conteudo = await arquivo.read()
    if len(conteudo) > get_settings().max_upload_mb * 1024 * 1024:
        raise DocumentoInvalido(f"{arquivo.filename} passa do limite de {get_settings().max_upload_mb} MB.")
    return extrair_texto(arquivo.filename or "arquivo", conteudo)


# --------------------------------------------------------------------------- #
class EditalOut(BaseModel):
    id: int
    nome_arquivo: str
    revisado: bool
    requisitos: RequisitosEdital


class CandidatoOut(BaseModel):
    id: int
    nome_arquivo: str
    nome: str


class FalhaUpload(BaseModel):
    nome_arquivo: str
    erro: str


class UploadCandidatosOut(BaseModel):
    adicionados: list[CandidatoOut]
    falhas: list[FalhaUpload]


class ResultadoBusca(CandidatoOut):
    similaridade: float


def _edital_out(e: Edital) -> EditalOut:
    return EditalOut(id=e.id, nome_arquivo=e.nome_arquivo, revisado=e.revisado,
                     requisitos=RequisitosEdital.model_validate(e.requisitos))


# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    return {"status": "ok", "llm": get_settings().llm_provider}


@app.post("/api/editais", response_model=EditalOut, status_code=201)
async def criar_edital(
    arquivo: UploadFile = File(...),
    session: Session = Depends(get_session),
    extractor: Extractor = Depends(get_extractor),
):
    try:
        texto = await _ler(arquivo)
        requisitos = extractor.edital(texto)
    except DocumentoInvalido as exc:
        raise HTTPException(422, str(exc)) from exc
    except ErroExtracao as exc:
        raise HTTPException(502, str(exc)) from exc
    if not requisitos.perfis:
        raise HTTPException(422, "Nenhum perfil profissional foi encontrado neste edital.")
    e = Edital(nome_arquivo=arquivo.filename, texto=texto, requisitos=requisitos.model_dump(mode="json"))
    session.add(e)
    session.commit()
    return _edital_out(e)


@app.get("/api/editais", response_model=list[EditalOut])
def listar_editais(session: Session = Depends(get_session)):
    return [_edital_out(e) for e in session.scalars(select(Edital).order_by(Edital.id.desc()))]


@app.get("/api/editais/{edital_id}", response_model=EditalOut)
def obter_edital(edital_id: int, session: Session = Depends(get_session)):
    e = session.get(Edital, edital_id)
    if not e:
        raise HTTPException(404, "Edital não encontrado.")
    return _edital_out(e)


@app.put("/api/editais/{edital_id}/requisitos", response_model=EditalOut)
def revisar_requisitos(edital_id: int, requisitos: RequisitosEdital, session: Session = Depends(get_session)):
    """Permite que uma pessoa corrija o que a IA extraiu antes de gerar o ranking."""
    e = session.get(Edital, edital_id)
    if not e:
        raise HTTPException(404, "Edital não encontrado.")
    if not requisitos.perfis:
        raise HTTPException(422, "O edital precisa ter pelo menos um cargo.")
    e.requisitos = requisitos.model_dump(mode="json")
    e.revisado = True
    session.commit()
    return _edital_out(e)


@app.post("/api/candidatos", response_model=UploadCandidatosOut, status_code=201)
async def adicionar_candidatos(
    arquivos: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
    extractor: Extractor = Depends(get_extractor),
    embedder: Embedder = Depends(get_embedder),
):
    adicionados, falhas = [], []
    for arq in arquivos:
        try:
            texto = await _ler(arq)
            perfil = extractor.candidato(texto)
        except (DocumentoInvalido, ErroExtracao) as exc:
            falhas.append(FalhaUpload(nome_arquivo=arq.filename or "", erro=str(exc)))
            continue
        c = Candidato(
            nome_arquivo=arq.filename, nome=perfil.nome, texto=texto,
            perfil=perfil.model_dump(mode="json"),
            embedding=embedder.embed([texto_para_busca(perfil)])[0],
        )
        session.add(c)
        session.commit()
        adicionados.append(CandidatoOut(id=c.id, nome_arquivo=c.nome_arquivo, nome=c.nome))
    return UploadCandidatosOut(adicionados=adicionados, falhas=falhas)


@app.get("/api/candidatos", response_model=list[CandidatoOut])
def listar_candidatos(session: Session = Depends(get_session)):
    return [CandidatoOut(id=c.id, nome_arquivo=c.nome_arquivo, nome=c.nome)
            for c in session.scalars(select(Candidato).order_by(Candidato.nome))]


@app.get("/api/candidatos/busca", response_model=list[ResultadoBusca])
def buscar_candidatos(
    q: str = Query(..., min_length=3, description="Ex.: experiência com Oracle e PL/SQL"),
    limite: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
):
    """Busca semântica no banco de currículos com pgvector."""
    vetor = embedder.embed([q])[0]
    distancia = Candidato.embedding.cosine_distance(vetor)
    linhas = session.execute(
        select(Candidato, distancia.label("d")).where(Candidato.embedding.is_not(None)).order_by(distancia).limit(limite)
    )
    return [ResultadoBusca(id=c.id, nome_arquivo=c.nome_arquivo, nome=c.nome, similaridade=round(1 - d, 3))
            for c, d in linhas]


@app.delete("/api/candidatos/{candidato_id}", status_code=204)
def remover_candidato(candidato_id: int, session: Session = Depends(get_session)):
    c = session.get(Candidato, candidato_id)
    if not c:
        raise HTTPException(404, "Candidato não encontrado.")
    session.delete(c)
    session.commit()


@app.get("/api/editais/{edital_id}/ranking", response_model=list[Ranking])
def ranking(
    edital_id: int,
    cargo: str | None = None,
    session: Session = Depends(get_session),
    scorer: Scorer = Depends(get_scorer),
):
    e = session.get(Edital, edital_id)
    if not e:
        raise HTTPException(404, "Edital não encontrado.")
    req = RequisitosEdital.model_validate(e.requisitos)
    perfis = [p for p in req.perfis if cargo is None or p.cargo == cargo]
    if not perfis:
        raise HTTPException(404, f"O edital não tem o cargo {cargo!r}.")
    candidatos = [PerfilCandidato.model_validate(c.perfil) for c in session.scalars(select(Candidato))]
    return [scorer.ranking(p, candidatos) for p in perfis]


@app.post("/api/exemplo", status_code=201)
def carregar_exemplo(
    session: Session = Depends(get_session),
    extractor: Extractor = Depends(get_extractor),
    embedder: Embedder = Depends(get_embedder),
):
    """Carrega o edital e os currículos fictícios de exemplo (funciona no modo demo)."""
    pasta = RAIZ / "samples" / "pdfs"
    texto = extrair_texto("edital.pdf", (pasta / "edital_vale_verde.pdf").read_bytes())
    e = Edital(nome_arquivo="edital_vale_verde.pdf", texto=texto,
               requisitos=extractor.edital(texto).model_dump(mode="json"))
    session.add(e)
    existentes = set(session.scalars(select(Candidato.nome_arquivo)))
    for pdf in sorted(pasta.glob("cv_*.pdf")):
        if pdf.name in existentes:
            continue
        texto = extrair_texto(pdf.name, pdf.read_bytes())
        perfil = extractor.candidato(texto)
        session.add(Candidato(nome_arquivo=pdf.name, nome=perfil.nome, texto=texto,
                              perfil=perfil.model_dump(mode="json"),
                              embedding=embedder.embed([texto_para_busca(perfil)])[0]))
    session.commit()
    return {"edital_id": e.id, "candidatos": session.query(Candidato).count()}


log = logging.getLogger("uvicorn.error")
_avaliacao: dict = {"status": "parada"}
_trava = threading.Lock()


def _rodar_avaliacao() -> None:
    from eval.run_eval import avaliar

    try:
        resultado = avaliar("llm", verbose=False, llm=get_llm())
        _avaliacao.update(status="concluida", resultado=resultado)
        log.info("AVALIACAO_LLM %s", json.dumps(resultado, ensure_ascii=False))
    except Exception as exc:  # o erro aparece para quem consultar a rota
        _avaliacao.update(status="erro", erro=f"{type(exc).__name__}: {exc}")
        log.exception("AVALIACAO_LLM falhou")


@app.get("/api/avaliacao", include_in_schema=False)
def avaliacao(token: str = Query(...), refazer: bool = False):
    """Roda a avaliação com o LLM configurado, em segundo plano. Protegida por ADMIN_TOKEN."""
    s = get_settings()
    if not s.admin_token or not secrets.compare_digest(token, s.admin_token):
        raise HTTPException(404, "Not Found")
    if s.llm_provider == "demo":
        raise HTTPException(409, "Configure LLM_PROVIDER e LLM_API_KEY para avaliar com IA.")
    with _trava:
        if _avaliacao["status"] != "rodando" and (refazer or _avaliacao["status"] == "parada"):
            _avaliacao.clear()
            _avaliacao.update(status="rodando", modelo=s.llm_model)
            threading.Thread(target=_rodar_avaliacao, daemon=True).start()
    return _avaliacao


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(RAIZ / "app" / "static" / "index.html")
