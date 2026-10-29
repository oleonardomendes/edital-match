"""Testes do RAG: divisão em trechos, busca híbrida, perguntas e importação do PNCP."""

import json
import os

import httpx
import pytest

from app.rag.chunking import dividir, eh_titulo

DB = os.getenv("TEST_DATABASE_URL")

FILLER = {
    "4. DAS CONDIÇÕES DE PARTICIPAÇÃO": "Poderão participar desta licitação os interessados cujo ramo de atividade seja compatível com o objeto, "
    "que estejam cadastrados no sistema de compras. Não poderão participar empresas suspensas ou declaradas inidôneas. ",
    "5. DA PROPOSTA DE PREÇOS": "A proposta deverá conter o preço unitário e total de cada item, em moeda corrente nacional, "
    "com validade mínima de 60 dias, incluídos todos os tributos, encargos sociais e despesas. ",
    "6. DA HABILITAÇÃO JURÍDICA E FISCAL": "Para habilitação serão exigidos o ato constitutivo, a prova de inscrição no CNPJ, "
    "as certidões de regularidade com a Fazenda Federal, Estadual e Municipal, o FGTS e a Justiça do Trabalho. ",
    "9. DAS SANÇÕES ADMINISTRATIVAS": "Pela inexecução total ou parcial do contrato, a Administração poderá aplicar advertência, "
    "multa de até 20% do valor do contrato, impedimento de licitar e declaração de inidoneidade. ",
    "10. DO PAGAMENTO": "O pagamento será efetuado em até 30 dias após o ateste da nota fiscal pelo fiscal do contrato, "
    "mediante depósito em conta corrente indicada pela contratada. ",
}

EQUIPE = """7. QUALIFICAÇÃO TÉCNICA
7.1 A licitante deverá indicar a equipe técnica mínima, cuja comprovação será exigida na assinatura do contrato.
7.2 GERENTE DE PROJETOS
Graduação em Tecnologia da Informação e experiência mínima de 5 anos em gestão de projetos de TI.
Certificação PMP emitida pelo PMI.
7.3 Será admitida a substituição de profissional por outro de experiência equivalente ou superior, mediante aprovação da Administração."""


def _paginas():
    filler = [f"{t}\n" + c * 6 for t, c in FILLER.items()]
    return ["PREGÃO ELETRÔNICO Nº 90012/2026\n1. DO OBJETO\nContratação de serviços de desenvolvimento de sistemas."] + filler[:3] + [EQUIPE] + filler[3:]


def test_titulos_de_secao():
    assert eh_titulo("7.2 GERENTE DE PROJETOS")
    assert eh_titulo("CLÁUSULA DÉCIMA - DAS PENALIDADES")
    assert eh_titulo("ANEXO I - TERMO DE REFERÊNCIA")
    assert not eh_titulo("Graduação em Tecnologia da Informação e experiência mínima de 5 anos em gestão de projetos de TI.")
    assert not eh_titulo("a)")


def test_trechos_guardam_pagina_e_secao():
    trechos = dividir(_paginas(), tamanho=400)
    gp = next(t for t in trechos if "PMP" in t.texto)
    assert gp.pagina == 5 and gp.secao == "7.2 GERENTE DE PROJETOS"
    assert all(len(t.texto) <= 600 for t in trechos)
    # Um trecho não mistura seções.
    assert not any("PMP" in t.texto and "pagamento" in t.texto.lower() for t in trechos)


def test_trecho_longo_tem_sobreposicao():
    texto = "\n".join(f"Linha {i} com algum conteúdo sobre o contrato e suas obrigações." for i in range(60))
    trechos = dividir([texto], tamanho=500, sobra=120)
    assert len(trechos) > 3
    fim_anterior = trechos[0].texto[-60:].split("\n")[-1]
    assert fim_anterior.split()[-1] in trechos[1].texto


# --------------------------------------------------------------------------- #
# PNCP com transporte falso (sem rede)


def _cliente_pncp(rotas):
    def handler(req: httpx.Request):
        for prefixo, resposta in rotas.items():
            if req.url.path.startswith(prefixo):
                return resposta(req) if callable(resposta) else resposta
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_pncp_busca_mapeia_campos():
    from app import pncp

    item = {"title": "Edital nº 3/2026", "description": "Fábrica de software", "orgao_nome": "TRIBUNAL", "municipio_nome": "Cuiabá",
            "uf": "MT", "modalidade_licitacao_nome": "Pregão - Eletrônico", "orgao_cnpj": "05901308000121", "ano": "2026",
            "numero_sequencial": "3", "valor_total_estimado": 100.0, "data_fim_vigencia": "2026-11-10T10:00"}
    c = _cliente_pncp({"/api/search/": httpx.Response(200, json={"items": [item, {"title": "sem id"}]})})
    r = pncp.buscar("fábrica de software", client=c)
    assert len(r) == 1 and r[0].sequencial == 3
    assert r[0].link == "https://pncp.gov.br/app/editais/05901308000121/2026/3"


def test_pncp_baixa_edital_e_abre_zip():
    import io
    import zipfile

    from app import pncp

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("docs/termo.txt", "Termo de referência com a equipe técnica.")
        z.writestr("docs/planilha.xlsx", "x")
    arquivos = [
        {"sequencialDocumento": 1, "titulo": "Edital", "tipoDocumentoNome": "Edital", "statusAtivo": True,
         "url": "https://pncp.gov.br/pncp-api/v1/orgaos/05901308000121/compras/2026/3/arquivos/1"},
        {"sequencialDocumento": 2, "titulo": "Aviso", "tipoDocumentoNome": "Aviso de Contratação Direta", "statusAtivo": True,
         "url": "https://pncp.gov.br/pncp-api/v1/orgaos/05901308000121/compras/2026/3/arquivos/2"},
    ]
    c = _cliente_pncp({
        "/api/pncp/v1/orgaos/05901308000121/compras/2026/3/arquivos": httpx.Response(200, json=arquivos),
        "/pncp-api/v1/orgaos/05901308000121/compras/2026/3/arquivos/1": httpx.Response(
            200, content=buf.getvalue(), headers={"content-disposition": 'attachment; filename="edital.zip"'}),
    })
    docs = pncp.baixar_documentos("05901308000121", 2026, 3, client=c)
    assert [n for n, _ in docs] == ["termo.txt"]


def test_pncp_cnpj_invalido():
    from app import pncp

    with pytest.raises(pncp.ErroPNCP):
        pncp.baixar_documentos("123", 2026, 1)


# --------------------------------------------------------------------------- #
# Busca híbrida e perguntas, com Postgres de verdade

pg = pytest.mark.skipif(not DB, reason="TEST_DATABASE_URL não definida")


@pytest.fixture(scope="module")
def sessao():
    os.environ.update(DATABASE_URL=DB or "", LLM_PROVIDER="demo", EMBEDDING_PROVIDER="hashing")
    from app import db
    from app.config import get_settings

    get_settings.cache_clear()
    db._engine = None
    db.criar_tabelas()
    from sqlalchemy.orm import Session

    with Session(db.engine()) as s:
        e = db.Edital(nome_arquivo="sintetico.txt", texto="\f".join(_paginas()), requisitos={"perfis": []})
        s.add(e)
        s.flush()
        yield s, e.id
        s.rollback()


@pg
def test_busca_hibrida_acha_a_secao_certa(sessao):
    from app.matching.embeddings import HashingEmbedder
    from app.rag.busca import buscar, indexar

    s, eid = sessao
    emb = HashingEmbedder()
    assert indexar(s, eid, _paginas(), emb) >= 8
    top = buscar(s, eid, "qual certificação o gerente de projetos precisa ter?", emb, k=3)
    assert top[0].secao == "7.2 GERENTE DE PROJETOS"
    assert "texto" in top[0].fontes
    # Sem acento na pergunta também funciona.
    top = buscar(s, eid, "substituicao de profissional", emb, k=2)
    assert any("substituição" in r.texto for r in top)


@pg
def test_contexto_de_extracao_respeita_limite_e_traz_equipe(sessao):
    from app.matching.embeddings import HashingEmbedder
    from app.rag.contexto import montar_contexto

    s, eid = sessao
    contexto, usados = montar_contexto(s, eid, HashingEmbedder(), limite=1500)
    assert len(contexto) <= 1500 + 50 * len(usados)
    assert "PMP" in contexto and "[p. 5" in contexto


@pg
def test_pergunta_no_modo_demo_devolve_trechos(sessao):
    from app.extraction.llm import SemLLM
    from app.matching.embeddings import HashingEmbedder
    from app.rag.perguntas import perguntar

    s, eid = sessao
    resposta, trechos, aviso = perguntar(s, eid, "quando a equipe técnica será comprovada?", HashingEmbedder(), SemLLM())
    assert resposta is None and aviso
    assert any("assinatura do contrato" in t.texto for t in trechos[:3])


@pg
def test_pergunta_com_llm_filtra_paginas_inventadas(sessao):
    from app.matching.embeddings import HashingEmbedder
    from app.rag.perguntas import RespostaEdital, perguntar

    class LLMFalso:
        def extrair(self, instrucoes, texto, schema):
            assert "[p. 5" in texto
            return RespostaEdital(encontrou=True, resposta="Na assinatura do contrato.", paginas=[5, 99])

    s, eid = sessao
    resposta, _, _ = perguntar(s, eid, "quando a equipe técnica será comprovada?", HashingEmbedder(), LLMFalso())
    assert resposta.paginas == [5]


def test_resposta_serializa():
    from app.rag.perguntas import RespostaEdital

    assert json.loads(RespostaEdital(encontrou=False, resposta="x").model_dump_json())["paginas"] == []
