"""Modelos de domínio: o que se extrai do edital, do currículo e o resultado da análise."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class NivelFormacao(str, Enum):
    """Níveis de formação em ordem crescente."""

    medio = "medio"
    tecnico = "tecnico"
    graduacao = "graduacao"
    pos_graduacao = "pos_graduacao"
    mestrado = "mestrado"
    doutorado = "doutorado"

    @property
    def ordem(self) -> int:
        return list(NivelFormacao).index(self)


# --------------------------------------------------------------------------- #
# Edital
# --------------------------------------------------------------------------- #


class RequisitoFormacao(BaseModel):
    nivel_minimo: NivelFormacao
    areas: list[str] = Field(
        default_factory=list,
        description="Áreas aceitas. Lista vazia aceita qualquer área.",
    )
    obrigatorio: bool = True
    peso: float = 1.0
    texto_original: str = ""


class RequisitoExperiencia(BaseModel):
    area: str = Field(description="Atividade ou área em que a experiência é exigida")
    anos_minimos: float
    obrigatorio: bool = True
    peso: float = 1.0
    texto_original: str = ""


class RequisitoCertificacao(BaseModel):
    nome: str
    alternativas: list[str] = Field(
        default_factory=list, description="Certificações equivalentes aceitas"
    )
    obrigatorio: bool = False
    peso: float = 1.0
    texto_original: str = ""


class RequisitoCompetencia(BaseModel):
    nome: str
    alternativas: list[str] = Field(
        default_factory=list, description="Opções equivalentes quando o edital diz 'X ou Y'"
    )
    obrigatorio: bool = False
    peso: float = 1.0
    texto_original: str = ""


class PerfilEdital(BaseModel):
    """Um perfil profissional exigido pelo edital (ex.: 'Gerente de Projetos')."""

    cargo: str
    quantidade: int | None = None
    formacao: list[RequisitoFormacao] = Field(default_factory=list)
    experiencias: list[RequisitoExperiencia] = Field(default_factory=list)
    certificacoes: list[RequisitoCertificacao] = Field(default_factory=list)
    competencias: list[RequisitoCompetencia] = Field(default_factory=list)


class RequisitosEdital(BaseModel):
    orgao: str | None = None
    numero: str | None = None
    objeto: str | None = None
    perfis: list[PerfilEdital]


# --------------------------------------------------------------------------- #
# Candidato
# --------------------------------------------------------------------------- #


class Formacao(BaseModel):
    nivel: NivelFormacao
    curso: str
    instituicao: str | None = None
    concluida: bool = True
    ano_conclusao: int | None = None


class Experiencia(BaseModel):
    cargo: str
    empresa: str | None = None
    inicio: date
    fim: date | None = Field(default=None, description="Vazio quando é o emprego atual")
    descricao: str = ""
    tecnologias: list[str] = Field(default_factory=list)


class Certificacao(BaseModel):
    nome: str
    emissor: str | None = None
    ano: int | None = None


class PerfilCandidato(BaseModel):
    nome: str
    formacoes: list[Formacao] = Field(default_factory=list)
    experiencias: list[Experiencia] = Field(default_factory=list)
    certificacoes: list[Certificacao] = Field(default_factory=list)
    competencias: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Resultado
# --------------------------------------------------------------------------- #


class StatusCriterio(str, Enum):
    atende = "atende"
    parcial = "parcial"
    nao_atende = "nao_atende"


class AvaliacaoCriterio(BaseModel):
    tipo: str  # formacao | experiencia | certificacao | competencia
    requisito: str
    obrigatorio: bool
    peso: float
    status: StatusCriterio
    pontuacao: float = Field(ge=0, le=1, description="Fração atendida (0 a 1)")
    evidencia: str
    justificativa: str


class ResultadoCandidato(BaseModel):
    candidato: str
    cargo: str
    score: float = Field(description="0 a 100")
    elegivel: bool = Field(description="Falso se algum requisito obrigatório não é atendido")
    criterios: list[AvaliacaoCriterio]
    resumo: str


class Ranking(BaseModel):
    cargo: str
    resultados: list[ResultadoCandidato]
