from __future__ import annotations

import json
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app import pncp
from app.db import Candidato, DbCache, Edital, Extracao, TrechoEdital, criar_tabelas, engine, get_session
from app.extraction.documents import DocumentoInvalido, extrair_paginas, extrair_texto, juntar_paginas
from app.extraction.extractor import Extractor
from app.extraction.llm import LLM, ErroExtracao
from app.matching.embeddings import Embedder
from app.matching.scorer import Scorer
from app.rag.busca import indexar, tem_indice
from app.rag.contexto import CONSULTAS_CARGOS, contexto_do_cargo, montar_contexto
from app.rag.perguntas import perguntar
from app.schemas import PerfilCandidato, PerfilEdital, Ranking, RequisitosEdital
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
    return Extractor(llm, DbCache(session), limite_edital=get_settings().edital_max_chars)


async def _bytes(arquivo: UploadFile) -> bytes:
    conteudo = await arquivo.read()
    if len(conteudo) > get_settings().max_upload_mb * 1024 * 1024:
        raise DocumentoInvalido(f"{arquivo.filename} passa do limite de {get_settings().max_upload_mb} MB.")
    return conteudo


async def _ler(arquivo: UploadFile) -> str:
    return extrair_texto(arquivo.filename or "arquivo", await _bytes(arquivo))


def _paginas_marcadas(paginas: list[str]) -> str:
    return "\n\n".join(f"[p. {n}]\n{p}" for n, p in enumerate(paginas, start=1) if p.strip())


def _processar_edital(nome: str, paginas: list[str], session: Session, extractor: Extractor, embedder: Embedder) -> Edital:
    """Indexa o edital e extrai os requisitos a partir dos trechos recuperados (RAG)."""
    texto = juntar_paginas(paginas)
    e = Edital(nome_arquivo=nome[:255], texto=texto, requisitos={"perfis": []})
    session.add(e)
    session.flush()
    try:
        indexar(session, e.id, paginas, embedder)
        limite = get_settings().edital_max_chars
        completo = _paginas_marcadas(paginas)
        if len(completo) <= limite:
            # Edital curto: vai inteiro, numa chamada só.
            requisitos = extractor.edital(texto, contexto=completo)
        else:
            # Edital longo: primeiro a lista de cargos; os requisitos de cada cargo são
            # extraídos depois, cada um com os trechos recuperados para ele.
            contexto = montar_contexto(session, e.id, embedder, limite, consultas=CONSULTAS_CARGOS, vizinhos=True)[0]
            lista = extractor.cargos(texto, contexto)
            requisitos = RequisitosEdital(
                orgao=lista.orgao, numero=lista.numero, objeto=lista.objeto, regras_equipe=lista.regras_equipe,
                perfis=[PerfilEdital(cargo=c.cargo, quantidade=c.quantidade, pagina=c.pagina, detalhado=False) for c in lista.cargos],
            )
    except Exception:
        session.rollback()
        raise
    # Muitos editais não listam perfis de equipe. O edital fica salvo mesmo
    # assim: dá para perguntar sobre ele e cadastrar os cargos na revisão.
    e.requisitos = requisitos.model_dump(mode="json")
    session.commit()
    return e


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
    embedder: Embedder = Depends(get_embedder),
):
    try:
        paginas = extrair_paginas(arquivo.filename or "arquivo", await _bytes(arquivo))
        e = _processar_edital(arquivo.filename or "edital", paginas, session, extractor, embedder)
    except DocumentoInvalido as exc:
        raise HTTPException(422, str(exc)) from exc
    except ErroExtracao as exc:
        raise HTTPException(502, str(exc)) from exc
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


class DetalharIn(BaseModel):
    cargo: str


@app.post("/api/editais/{edital_id}/perfis/detalhar", response_model=EditalOut)
def detalhar_perfil(
    edital_id: int,
    body: DetalharIn,
    session: Session = Depends(get_session),
    extractor: Extractor = Depends(get_extractor),
    embedder: Embedder = Depends(get_embedder),
):
    """Etapa 2 da extração: busca os trechos de um cargo e extrai os requisitos dele."""
    e = session.get(Edital, edital_id)
    if not e:
        raise HTTPException(404, "Edital não encontrado.")
    req = RequisitosEdital.model_validate(e.requisitos)
    i = next((i for i, p in enumerate(req.perfis) if p.cargo == body.cargo), None)
    if i is None:
        raise HTTPException(404, f"O edital não tem o cargo {body.cargo!r}.")
    _garantir_indice(e, session, embedder)
    contexto = contexto_do_cargo(session, e.id, body.cargo, embedder, get_settings().edital_max_chars)
    try:
        novo = extractor.perfil(e.texto, body.cargo, contexto)
    except ErroExtracao as exc:
        raise HTTPException(502, str(exc)) from exc
    atual = req.perfis[i]
    req.perfis[i] = novo.model_copy(update={"cargo": atual.cargo, "quantidade": atual.quantidade or novo.quantidade,
                                            "pagina": atual.pagina or novo.pagina, "detalhado": True})
    e.requisitos = req.model_dump(mode="json")
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
    if not perfis and cargo is None:
        return []
    if not perfis:
        raise HTTPException(404, f"O edital não tem o cargo {cargo!r}.")
    candidatos = [PerfilCandidato.model_validate(c.perfil) for c in session.scalars(select(Candidato))]
    # Cargo ainda sem requisitos extraídos não tem ranking.
    return [scorer.ranking(p, candidatos) if p.detalhado else Ranking(cargo=p.cargo, resultados=[]) for p in perfis]


@app.post("/api/exemplo", status_code=201)
def carregar_exemplo(
    session: Session = Depends(get_session),
    extractor: Extractor = Depends(get_extractor),
    embedder: Embedder = Depends(get_embedder),
):
    """Carrega o edital e os currículos fictícios de exemplo (funciona no modo demo)."""
    pasta = RAIZ / "samples" / "pdfs"
    paginas = extrair_paginas("edital.pdf", (pasta / "edital_vale_verde.pdf").read_bytes())
    e = _processar_edital("edital_vale_verde.pdf", paginas, session, extractor, embedder)
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


# --------------------------------------------------------------------------- #
# RAG: perguntas sobre o edital
class PerguntaIn(BaseModel):
    pergunta: str = Field(min_length=5, max_length=500)


class TrechoOut(BaseModel):
    pagina: int
    secao: str
    texto: str
    score: float
    fontes: list[str]


class RespostaOut(BaseModel):
    pergunta: str
    encontrou: bool | None
    resposta: str | None
    paginas: list[int]
    trechos: list[TrechoOut]
    aviso: str | None = None


def _garantir_indice(e: Edital, session: Session, embedder: Embedder) -> None:
    """Editais enviados antes do RAG são indexados na primeira pergunta."""
    if not tem_indice(session, e.id):
        indexar(session, e.id, e.texto.split("\f"), embedder)
        session.commit()


@app.post("/api/editais/{edital_id}/perguntas", response_model=RespostaOut)
def perguntar_ao_edital(
    edital_id: int,
    body: PerguntaIn,
    session: Session = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
    llm: LLM = Depends(get_llm),
):
    e = session.get(Edital, edital_id)
    if not e:
        raise HTTPException(404, "Edital não encontrado.")
    _garantir_indice(e, session, embedder)
    resposta, trechos, erro = perguntar(session, edital_id, body.pergunta, embedder, llm)
    if erro and get_settings().llm_provider == "demo":
        erro = "Modo demo: sem chave de IA, a resposta não é gerada. Abaixo estão os trechos que a busca encontrou."
    return RespostaOut(
        pergunta=body.pergunta,
        encontrou=resposta.encontrou if resposta else None,
        resposta=resposta.resposta if resposta else None,
        paginas=resposta.paginas if resposta else [],
        trechos=[TrechoOut(pagina=t.pagina, secao=t.secao, texto=t.texto, score=round(t.score, 4), fontes=t.fontes) for t in trechos],
        aviso=erro,
    )


@app.get("/api/editais/{edital_id}/trechos", response_model=list[TrechoOut])
def listar_trechos(edital_id: int, session: Session = Depends(get_session), embedder: Embedder = Depends(get_embedder)):
    """Trechos indexados do edital, na ordem do documento."""
    e = session.get(Edital, edital_id)
    if not e:
        raise HTTPException(404, "Edital não encontrado.")
    _garantir_indice(e, session, embedder)
    linhas = session.scalars(select(TrechoEdital).where(TrechoEdital.edital_id == edital_id).order_by(TrechoEdital.ordem))
    return [TrechoOut(pagina=t.pagina, secao=t.secao, texto=t.texto, score=0, fontes=[]) for t in linhas]


# --------------------------------------------------------------------------- #
# PNCP: editais públicos
class ContratacaoOut(BaseModel):
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
    link: str


class ImportarIn(BaseModel):
    cnpj: str = Field(pattern=r"^\d{14}$")
    ano: int = Field(ge=2021, le=2100)
    sequencial: int = Field(ge=1)


@app.get("/api/pncp/busca", response_model=list[ContratacaoOut])
def buscar_pncp(q: str = Query(..., min_length=3), pagina: int = Query(1, ge=1, le=20), abertas: bool = True):
    try:
        itens = pncp.buscar(q, pagina=pagina, abertas=abertas)
    except pncp.ErroPNCP as exc:
        raise HTTPException(502, str(exc)) from exc
    return [ContratacaoOut(**{**i.__dict__, "link": i.link}) for i in itens]


@app.post("/api/pncp/importar", response_model=EditalOut, status_code=201)
def importar_pncp(
    body: ImportarIn,
    session: Session = Depends(get_session),
    extractor: Extractor = Depends(get_extractor),
    embedder: Embedder = Depends(get_embedder),
):
    try:
        documentos = pncp.baixar_documentos(body.cnpj, body.ano, body.sequencial, limite_mb=get_settings().max_upload_mb * 3)
        paginas: list[str] = []
        for nome, conteudo in documentos:
            try:
                paginas.extend(extrair_paginas(nome, conteudo))
            except DocumentoInvalido:
                continue  # um anexo escaneado não impede a leitura dos outros
        if not paginas:
            raise DocumentoInvalido("Nenhum arquivo da contratação tem texto selecionável (podem ser PDFs escaneados).")
        e = _processar_edital(f"PNCP {body.cnpj}/{body.ano}/{body.sequencial}", paginas, session, extractor, embedder)
    except pncp.ErroPNCP as exc:
        raise HTTPException(502, str(exc)) from exc
    except DocumentoInvalido as exc:
        raise HTTPException(422, str(exc)) from exc
    except ErroExtracao as exc:
        raise HTTPException(502, str(exc)) from exc
    return _edital_out(e)


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


def _admin(token: str) -> None:
    s = get_settings()
    if not s.admin_token or not secrets.compare_digest(token, s.admin_token):
        raise HTTPException(404, "Not Found")


@app.get("/api/avaliacao-busca", include_in_schema=False)
def avaliacao_busca(
    token: str = Query(...),
    edital_id: int = Query(...),
    conjunto: str = Query(...),
    rrf_k: int = 60,
    norm: int = 0,
    candidatos: int = 20,
    session: Session = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
):
    """Mede a recuperação de trechos (acerto@k, MRR) num edital já importado. Protegida por ADMIN_TOKEN."""
    _admin(token)
    from eval.busca import avaliar_busca, carregar_gabarito

    e = session.get(Edital, edital_id)
    if not e:
        raise HTTPException(404, "Edital não encontrado.")
    try:
        gab = carregar_gabarito(conjunto)
    except KeyError as exc:
        raise HTTPException(404, f"Conjunto {conjunto!r} não existe no gabarito.") from exc
    _garantir_indice(e, session, embedder)
    resultado = avaliar_busca(session, edital_id, gab["perguntas"], embedder, rrf_k=rrf_k, norm=norm, candidatos=candidatos)
    resultado["embedder"] = get_settings().embedding_provider
    log.info("AVALIACAO_BUSCA %s %s", conjunto, json.dumps(resultado, ensure_ascii=False))
    return resultado


@app.post("/api/admin/reindexar", include_in_schema=False)
def reindexar(token: str = Query(...), edital_id: int | None = None, session: Session = Depends(get_session),
              embedder: Embedder = Depends(get_embedder)):
    """Recalcula embeddings de editais e currículos, por exemplo depois de trocar o modelo de embeddings."""
    _admin(token)
    consulta = select(Edital) if edital_id is None else select(Edital).where(Edital.id == edital_id)
    editais = list(session.scalars(consulta))
    for e in editais:
        indexar(session, e.id, e.texto.split("\f"), embedder)
    candidatos = list(session.scalars(select(Candidato)))
    for c in candidatos:
        c.embedding = embedder.embed([texto_para_busca(PerfilCandidato.model_validate(c.perfil))])[0]
    session.commit()
    return {"editais": len(editais), "candidatos": len(candidatos)}


@app.get("/api/admin/contexto", include_in_schema=False)
def ver_contexto(token: str, edital_id: int, cargo: str | None = None, session: Session = Depends(get_session),
                 embedder: Embedder = Depends(get_embedder)):
    """Diagnóstico: o contexto que o RAG monta para a lista de cargos ou para um cargo."""
    _admin(token)
    limite = get_settings().edital_max_chars
    if cargo:
        return {"contexto": contexto_do_cargo(session, edital_id, cargo, embedder, limite)}
    texto, usados = montar_contexto(session, edital_id, embedder, limite, consultas=CONSULTAS_CARGOS, vizinhos=True)
    return {"contexto": texto, "trechos": [{"pagina": r.pagina, "fontes": r.fontes} for r in usados]}


@app.get("/api/admin/pdf-teste", include_in_schema=False)
def pdf_teste(token: str, cnpj: str, ano: int, sequencial: int, inicio: int, fim: int, modo: str = "layout"):
    """Diagnóstico: texto de páginas de um PDF do PNCP em cada modo de extração do pypdf."""
    _admin(token)
    import io as _io

    from pypdf import PdfReader

    saida = []
    for nome, conteudo in pncp.baixar_documentos(cnpj, ano, sequencial):
        if not nome.lower().endswith(".pdf"):
            continue
        r = PdfReader(_io.BytesIO(conteudo))
        for n in range(inicio - 1, min(fim, len(r.pages))):
            saida.append({"arquivo": nome, "pagina": n + 1, "texto": r.pages[n].extract_text(extraction_mode=modo)})
    return saida


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(RAIZ / "app" / "static" / "index.html")
