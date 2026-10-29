"""Compara o que o LLM extraiu com o gabarito escrito à mão.

Mede a extração campo a campo, separada das decisões do motor: assim dá para
saber se um erro no ranking veio da leitura do documento ou das regras.
"""

from __future__ import annotations

from app.matching.scorer import anos_de_experiencia
from app.matching.text import mesmo_item
from app.schemas import PerfilCandidato, PerfilEdital, RequisitosEdital

TIPOS = ("formacao", "experiencias", "certificacoes", "competencias")


def _nome(tipo: str, r) -> str:
    if tipo == "formacao":
        return r.nivel_minimo.value
    if tipo == "experiencias":
        return r.area
    return r.nome


def _casa(tipo: str, a, b) -> bool:
    if tipo == "formacao":
        return a.nivel_minimo == b.nivel_minimo
    if tipo == "experiencias":
        return mesmo_item(a.area, b.area, limiar=70) and abs(a.anos_minimos - b.anos_minimos) < 0.01
    nomes_b = [b.nome, *b.alternativas]
    return any(mesmo_item(n, m) for n in [a.nome, *a.alternativas] for m in nomes_b)


def achar_cargo(perfis: list[PerfilEdital], cargo: str) -> PerfilEdital | None:
    return next((p for p in perfis if mesmo_item(p.cargo, cargo, limiar=80)), None)


def comparar_edital(extraido: RequisitosEdital, gabarito: RequisitosEdital) -> dict:
    encontrados = obrig_ok = total = sobrando = 0
    faltando: list[str] = []
    for pg in gabarito.perfis:
        pe = achar_cargo(extraido.perfis, pg.cargo)
        for tipo in TIPOS:
            esperados = getattr(pg, tipo)
            obtidos = list(getattr(pe, tipo)) if pe else []
            total += len(esperados)
            for r in esperados:
                par = next((o for o in obtidos if _casa(tipo, o, r)), None)
                if par is None:
                    faltando.append(f"{pg.cargo}: {tipo} {_nome(tipo, r)}")
                    continue
                obtidos.remove(par)
                encontrados += 1
                obrig_ok += par.obrigatorio == r.obrigatorio
            sobrando += len(obtidos)
    return {
        "cargos_encontrados": sum(achar_cargo(extraido.perfis, p.cargo) is not None for p in gabarito.perfis),
        "cargos_esperados": len(gabarito.perfis),
        "requisitos_encontrados": encontrados,
        "requisitos_esperados": total,
        "obrigatoriedade_correta": obrig_ok,
        "requisitos_a_mais": sobrando,
        "faltando": faltando,
    }


def comparar_cv(extraido: PerfilCandidato, gabarito: PerfilCandidato, referencia) -> dict:
    anos_e = anos_de_experiencia(extraido.experiencias, referencia)
    anos_g = anos_de_experiencia(gabarito.experiencias, referencia)
    cert_ok = sum(any(mesmo_item(c.nome, e.nome) for e in extraido.certificacoes) for c in gabarito.certificacoes)
    form_ok = sum(
        any(e.nivel == g.nivel and e.concluida == g.concluida and mesmo_item(e.curso, g.curso, limiar=70) for e in extraido.formacoes)
        for g in gabarito.formacoes
    )
    return {
        "nome_ok": mesmo_item(extraido.nome, gabarito.nome),
        "experiencias": (len(extraido.experiencias), len(gabarito.experiencias)),
        "diferenca_anos": round(abs(anos_e - anos_g), 2),
        "certificacoes_ok": (cert_ok, len(gabarito.certificacoes)),
        "formacoes_ok": (form_ok, len(gabarito.formacoes)),
    }
