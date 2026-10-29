"""Testes de ponta a ponta da API com Postgres + pgvector de verdade.

Rodam quando TEST_DATABASE_URL está definida (no CI, um container pgvector).
Usam o modo demo, então não chamam nenhum LLM.
"""

import os
from pathlib import Path

import pytest

DB = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB, reason="TEST_DATABASE_URL não definida")

PDFS = Path(__file__).resolve().parent.parent / "samples" / "pdfs"


@pytest.fixture(scope="module")
def client():
    os.environ.update(DATABASE_URL=DB, LLM_PROVIDER="demo", EMBEDDING_PROVIDER="hashing")
    from fastapi.testclient import TestClient

    from app import db
    from app.config import get_settings

    get_settings.cache_clear()
    db._engine = None
    from app.main import app

    eng = db.engine()
    db.Base.metadata.drop_all(eng)
    with TestClient(app) as c:
        yield c
    db.Base.metadata.drop_all(eng)


def _enviar(client, rota, nomes, campo):
    arquivos = [(campo, (n, (PDFS / n).read_bytes(), "application/pdf")) for n in nomes]
    return client.post(rota, files=arquivos)


def test_fluxo_completo(client):
    r = _enviar(client, "/api/editais", ["edital_vale_verde.pdf"], "arquivo")
    assert r.status_code == 201, r.text
    edital = r.json()
    assert [p["cargo"] for p in edital["requisitos"]["perfis"]] == ["Gerente de Projetos", "Analista de Sistemas Sênior"]

    cvs = sorted(p.name for p in PDFS.glob("cv_*.pdf"))
    r = _enviar(client, "/api/candidatos", cvs, "arquivos")
    assert r.status_code == 201
    assert len(r.json()["adicionados"]) == 8 and r.json()["falhas"] == []

    r = client.get(f"/api/editais/{edital['id']}/ranking", params={"cargo": "Analista de Sistemas Sênior"})
    assert r.status_code == 200
    resultados = r.json()[0]["resultados"]
    aptos = [x["candidato"] for x in resultados if x["elegivel"]]
    assert aptos[:2] == ["Bruno Henrique Sales", "Juliana Matos Ferreira"]
    assert all(c["evidencia"] for c in resultados[0]["criterios"])


def test_busca_semantica_usa_pgvector(client):
    r = client.get("/api/candidatos/busca", params={"q": "Java Oracle PL/SQL desenvolvimento de sistemas", "limite": 3})
    assert r.status_code == 200
    nomes = [x["nome"] for x in r.json()]
    assert len(nomes) == 3 and "Thiago Moreira Campos" not in nomes


def test_revisao_humana_dos_requisitos_e_salva(client):
    edital = client.get("/api/editais").json()[0]
    req = edital["requisitos"]
    # A pessoa revisora decide que PL/SQL não é obrigatório.
    analista = req["perfis"][1]
    for c in analista["competencias"]:
        if c["nome"] == "PL/SQL":
            c["obrigatorio"] = False
    r = client.put(f"/api/editais/{edital['id']}/requisitos", json=req)
    assert r.status_code == 200 and r.json()["revisado"] is True
    plsql = next(c for c in r.json()["requisitos"]["perfis"][1]["competencias"] if c["nome"] == "PL/SQL")
    assert plsql["obrigatorio"] is False


def test_carregar_exemplo(client):
    r = client.post("/api/exemplo")
    assert r.status_code == 201
    assert r.json()["candidatos"] >= 8


def test_documento_fora_dos_exemplos_no_modo_demo(client):
    r = client.post("/api/candidatos", files=[("arquivos", ("novo.txt", "Fulano de Tal. Desenvolvedor Python desde 2020 com FastAPI.".encode(), "text/plain"))])
    assert r.status_code == 201
    assert r.json()["falhas"][0]["erro"].startswith("Modo demo")


def test_formato_invalido(client):
    r = client.post("/api/editais", files=[("arquivo", ("edital.xlsx", b"x" * 100, "application/octet-stream"))])
    assert r.status_code == 422
    assert "Formato não suportado" in r.json()["detail"]


def test_requisitos_de_cada_edital_mudam_o_resultado(client):
    """Se este edital não exigir PMP, a Camila (que tem CAPM) passa a ser apta."""
    edital = client.get("/api/editais").json()[-1]
    ranking = lambda: client.get(f"/api/editais/{edital['id']}/ranking", params={"cargo": "Gerente de Projetos"}).json()[0]["resultados"]
    apta = lambda: next(r for r in ranking() if r["candidato"] == "Camila Rocha Prado")["elegivel"]
    assert apta() is False

    req = edital["requisitos"]
    pmp = next(c for c in req["perfis"][0]["certificacoes"] if c["nome"] == "PMP")
    pmp["obrigatorio"], pmp["peso"] = False, 2
    assert client.put(f"/api/editais/{edital['id']}/requisitos", json=req).status_code == 200
    assert apta() is True


def test_revisao_rejeita_peso_negativo(client):
    edital = client.get("/api/editais").json()[-1]
    req = edital["requisitos"]
    req["perfis"][0]["competencias"][0]["peso"] = -1
    r = client.put(f"/api/editais/{edital['id']}/requisitos", json=req)
    assert r.status_code == 422


def test_avaliacao_exige_token(client):
    assert client.get("/api/avaliacao", params={"token": "qualquer"}).status_code == 404


def test_pergunte_ao_edital_no_modo_demo(client):
    edital = client.get("/api/editais").json()[0]
    r = client.post(f"/api/editais/{edital['id']}/perguntas", json={"pergunta": "Qual certificação o gerente de projetos precisa?"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["resposta"] is None and corpo["aviso"].startswith("Modo demo")
    assert any("PMP" in t["texto"] for t in corpo["trechos"][:2])
    assert all(t["pagina"] >= 1 for t in corpo["trechos"])


def test_trechos_do_edital(client):
    edital = client.get("/api/editais").json()[0]
    trechos = client.get(f"/api/editais/{edital['id']}/trechos").json()
    assert [t["secao"] for t in trechos][:2] == ["1. OBJETO", "2. EQUIPE TÉCNICA MÍNIMA"]


def test_importar_do_pncp(client, monkeypatch):
    """Importa os arquivos de uma contratação (aqui, o edital de exemplo no lugar do download)."""
    from app import pncp

    pdf = (PDFS / "edital_vale_verde.pdf").read_bytes()
    monkeypatch.setattr(pncp, "baixar_documentos", lambda *a, **k: [("edital.pdf", pdf), ("anexo.xlsx", b"x")])
    r = client.post("/api/pncp/importar", json={"cnpj": "05901308000121", "ano": 2026, "sequencial": 3})
    assert r.status_code == 201, r.text
    assert r.json()["nome_arquivo"] == "PNCP 05901308000121/2026/3"
    assert client.post("/api/pncp/importar", json={"cnpj": "123", "ano": 2026, "sequencial": 3}).status_code == 422


def test_erro_do_pncp_vira_502(client, monkeypatch):
    from app import pncp

    def falha(*a, **k):
        raise pncp.ErroPNCP("O PNCP limitou o número de consultas.")

    monkeypatch.setattr(pncp, "buscar", falha)
    r = client.get("/api/pncp/busca", params={"q": "software"})
    assert r.status_code == 502 and "limitou" in r.json()["detail"]


def test_avaliacao_da_busca_no_exemplo(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_token", "segredo")
    edital = next(e for e in client.get("/api/editais").json() if e["nome_arquivo"] == "edital_vale_verde.pdf")
    r = client.get("/api/avaliacao-busca", params={"token": "segredo", "edital_id": edital["id"], "conjunto": "vale_verde"})
    assert r.status_code == 200, r.text
    m = r.json()["metodos"]["hibrida"]
    assert m["acerto@3"] == 1.0
    assert client.post("/api/admin/reindexar", params={"token": "errado"}).status_code == 404
    assert client.post("/api/admin/reindexar", params={"token": "segredo"}).json()["candidatos"] >= 8
