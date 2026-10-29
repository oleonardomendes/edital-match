"""Motor de pontuação.

A IA só extrai dados (do edital e dos currículos). A decisão é feita aqui, por
regras determinísticas, para que cada nota seja explicável e reproduzível: a
mesma entrada sempre gera o mesmo score e cada critério traz a evidência do CV
que o justifica.
"""

from __future__ import annotations

from datetime import date

from app.matching.similarity import LexicalSimilarity, Similarity
from app.matching.text import contem_termo, mesmo_item
from app.schemas import (
    AvaliacaoCriterio,
    Experiencia,
    NivelFormacao,
    PerfilCandidato,
    PerfilEdital,
    Ranking,
    RequisitoCertificacao,
    RequisitoCompetencia,
    RequisitoExperiencia,
    RequisitoFormacao,
    ResultadoCandidato,
    StatusCriterio,
)

ROTULO_NIVEL = {
    NivelFormacao.medio: "ensino médio",
    NivelFormacao.tecnico: "técnico",
    NivelFormacao.graduacao: "graduação",
    NivelFormacao.pos_graduacao: "pós-graduação",
    NivelFormacao.mestrado: "mestrado",
    NivelFormacao.doutorado: "doutorado",
}


def _status(p: float) -> StatusCriterio:
    if p >= 1:
        return StatusCriterio.atende
    if p > 0:
        return StatusCriterio.parcial
    return StatusCriterio.nao_atende


def anos_de_experiencia(experiencias: list[Experiencia], referencia: date) -> float:
    """Soma os períodos sem contar duas vezes os meses em que há sobreposição."""
    intervalos = sorted((e.inicio, min(e.fim or referencia, referencia)) for e in experiencias)
    total_dias, atual_ini, atual_fim = 0, None, None
    for ini, fim in intervalos:
        if fim <= ini:
            continue
        if atual_fim is None or ini > atual_fim:
            if atual_fim is not None:
                total_dias += (atual_fim - atual_ini).days
            atual_ini, atual_fim = ini, fim
        else:
            atual_fim = max(atual_fim, fim)
    if atual_fim is not None:
        total_dias += (atual_fim - atual_ini).days
    return total_dias / 365.25


class Scorer:
    def __init__(self, similarity: Similarity | None = None, referencia: date | None = None) -> None:
        self.sim = similarity or LexicalSimilarity()
        self.referencia = referencia or date.today()

    # ------------------------------------------------------------------ #
    def avaliar(self, perfil: PerfilEdital, cand: PerfilCandidato) -> ResultadoCandidato:
        criterios = (
            [self._formacao(r, cand) for r in perfil.formacao]
            + [self._experiencia(r, cand) for r in perfil.experiencias]
            + [self._certificacao(r, cand) for r in perfil.certificacoes]
            + [self._competencia(r, cand) for r in perfil.competencias]
        )
        peso_total = sum(c.peso for c in criterios) or 1.0
        score = round(100 * sum(c.peso * c.pontuacao for c in criterios) / peso_total, 1)
        pendentes = [c for c in criterios if c.obrigatorio and c.status != StatusCriterio.atende]
        return ResultadoCandidato(
            candidato=cand.nome,
            cargo=perfil.cargo,
            score=score,
            elegivel=not pendentes,
            criterios=criterios,
            resumo=self._resumo(criterios, pendentes),
        )

    def ranking(self, perfil: PerfilEdital, candidatos: list[PerfilCandidato]) -> Ranking:
        resultados = [self.avaliar(perfil, c) for c in candidatos]
        resultados.sort(key=lambda r: (r.elegivel, r.score), reverse=True)
        return Ranking(cargo=perfil.cargo, resultados=resultados)

    # ------------------------------------------------------------------ #
    def _formacao(self, req: RequisitoFormacao, cand: PerfilCandidato) -> AvaliacaoCriterio:
        rotulo = ROTULO_NIVEL[req.nivel_minimo]
        descricao = f"{rotulo.capitalize()} ou superior" + (f" em {', '.join(req.areas)}" if req.areas else "")
        melhor, evid, motivo = 0.0, "Nenhuma formação informada no currículo.", ""

        for f in cand.formacoes:
            nivel_ok = f.nivel.ordem >= req.nivel_minimo.ordem
            area_ok = not req.areas or any(
                mesmo_item(f.curso, a) or self.sim.score(a, f.curso) >= self.sim.limiar for a in req.areas
            )
            p = 1.0 if (nivel_ok and area_ok) else 0.5 if (nivel_ok or area_ok) else 0.0
            if p == 1.0 and not f.concluida:
                p, m = 0.5, "curso ainda não concluído"
            elif p == 1.0:
                m = "nível e área atendem"
            elif nivel_ok:
                m = "nível atende, mas a área do curso não corresponde"
            elif area_ok:
                m = f"área corresponde, mas o nível é inferior a {rotulo}"
            else:
                m = "nível e área não correspondem"
            if p > melhor or (p == melhor and not motivo):
                melhor, motivo = p, m
                situacao = "" if f.concluida else " (em andamento)"
                evid = f"{ROTULO_NIVEL[f.nivel].capitalize()} em {f.curso}{situacao}" + (
                    f", {f.instituicao}" if f.instituicao else ""
                )

        return self._criterio("formacao", descricao, req.obrigatorio, req.peso, melhor, evid,
                              motivo or "Sem formação para comparar.")

    def _experiencia(self, req: RequisitoExperiencia, cand: PerfilCandidato) -> AvaliacaoCriterio:
        relevantes = [
            e for e in cand.experiencias
            if self.sim.score(req.area, f"{e.cargo}. {e.descricao}") >= self.sim.limiar
        ]
        anos = anos_de_experiencia(relevantes, self.referencia)
        p = min(1.0, anos / req.anos_minimos) if req.anos_minimos > 0 else (1.0 if relevantes else 0.0)
        descricao = f"{_fmt_anos(req.anos_minimos)} de experiência em {req.area}"
        if relevantes:
            evid = "; ".join(_descrever_experiencia(e) for e in relevantes)
        else:
            evid = "Nenhuma experiência relacionada encontrada."
        just = f"{_fmt_anos(anos)} comprovados na área, de {_fmt_anos(req.anos_minimos)} exigidos."
        return self._criterio("experiencia", descricao, req.obrigatorio, req.peso, round(p, 3), evid, just)

    def _certificacao(self, req: RequisitoCertificacao, cand: PerfilCandidato) -> AvaliacaoCriterio:
        aceitas = [req.nome, *req.alternativas]
        achada = next((c for c in cand.certificacoes if any(mesmo_item(c.nome, a) for a in aceitas)), None)
        descricao = f"Certificação {req.nome}" + (f" (ou {', '.join(req.alternativas)})" if req.alternativas else "")
        if achada:
            evid = achada.nome + (f", {achada.ano}" if achada.ano else "")
            return self._criterio("certificacao", descricao, req.obrigatorio, req.peso, 1.0, evid,
                                  "Certificação equivalente encontrada no currículo.")
        return self._criterio("certificacao", descricao, req.obrigatorio, req.peso, 0.0,
                              "Não consta no currículo.", "Certificação não encontrada no currículo.")

    def _competencia(self, req: RequisitoCompetencia, cand: PerfilCandidato) -> AvaliacaoCriterio:
        aceitas = [req.nome, *req.alternativas]
        descricao = f"Conhecimento em {' ou '.join(aceitas)}"
        hab = next((c for c in cand.competencias if any(mesmo_item(c, a) for a in aceitas)), None)
        if hab:
            return self._criterio("competencia", descricao, req.obrigatorio, req.peso, 1.0,
                                  f"Listada nas competências: {hab}", "Competência declarada no currículo.")
        for e in cand.experiencias:
            tec = next((t for t in e.tecnologias if any(mesmo_item(t, a) for a in aceitas)), None)
            if tec or any(contem_termo(f"{e.cargo} {e.descricao}", a) for a in aceitas):
                local = f"{e.cargo}" + (f" na {e.empresa}" if e.empresa else "")
                return self._criterio("competencia", descricao, req.obrigatorio, req.peso, 1.0,
                                      f"Usada como {local}", "Competência aplicada em experiência profissional.")
        return self._criterio("competencia", descricao, req.obrigatorio, req.peso, 0.0,
                              "Não consta no currículo.", "Competência não encontrada no currículo.")

    # ------------------------------------------------------------------ #
    @staticmethod
    def _criterio(tipo, requisito, obrigatorio, peso, pontuacao, evidencia, justificativa) -> AvaliacaoCriterio:
        return AvaliacaoCriterio(
            tipo=tipo, requisito=requisito, obrigatorio=obrigatorio, peso=peso,
            status=_status(pontuacao), pontuacao=pontuacao, evidencia=evidencia, justificativa=justificativa,
        )

    @staticmethod
    def _resumo(criterios: list[AvaliacaoCriterio], pendentes: list[AvaliacaoCriterio]) -> str:
        atende = sum(1 for c in criterios if c.status == StatusCriterio.atende)
        base = f"Atende {atende} de {len(criterios)} critérios."
        if pendentes:
            lista = "; ".join(c.requisito for c in pendentes)
            return f"{base} Lacuna em item exigido: {lista}."
        return f"{base} Cobre todos os itens exigidos."


def _descrever_experiencia(e: Experiencia) -> str:
    local = f"{e.cargo} na {e.empresa}" if e.empresa else e.cargo
    periodo = f"{e.inicio:%m/%Y} a {e.fim:%m/%Y}" if e.fim else f"desde {e.inicio:%m/%Y}"
    return f"{local} ({periodo})"


def _fmt_anos(anos: float) -> str:
    if anos == int(anos):
        n = int(anos)
        return f"{n} ano" if n == 1 else f"{n} anos"
    return f"{anos:.1f} anos".replace(".", ",")
