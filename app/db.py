from __future__ import annotations

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, String, Text, create_engine, select, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class Edital(Base):
    __tablename__ = "editais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome_arquivo: Mapped[str] = mapped_column(String(255))
    texto: Mapped[str] = mapped_column(Text)
    requisitos: Mapped[dict] = mapped_column(JSONB)
    revisado: Mapped[bool] = mapped_column(default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class Candidato(Base):
    __tablename__ = "candidatos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome_arquivo: Mapped[str] = mapped_column(String(255))
    nome: Mapped[str] = mapped_column(String(255))
    texto: Mapped[str] = mapped_column(Text)
    perfil: Mapped[dict] = mapped_column(JSONB)
    embedding = mapped_column(Vector(), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class TrechoEdital(Base):
    """Pedaço do edital indexado para a busca híbrida (vetor + texto)."""

    __tablename__ = "trechos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    edital_id: Mapped[int] = mapped_column(ForeignKey("editais.id", ondelete="CASCADE"), index=True)
    ordem: Mapped[int] = mapped_column(Integer)
    pagina: Mapped[int] = mapped_column(Integer)
    secao: Mapped[str] = mapped_column(Text, default="")
    texto: Mapped[str] = mapped_column(Text)
    # Texto sem acentos e em minúsculas: a busca acha "qualificacao" e "qualificação".
    texto_busca: Mapped[str] = mapped_column(Text)
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('portuguese', texto_busca)", persisted=True))
    embedding = mapped_column(Vector(), nullable=True)

    __table_args__ = (Index("ix_trechos_tsv", "tsv", postgresql_using="gin"),)


class Extracao(Base):
    """Cache de extrações do LLM, indexado pelo hash do texto."""

    __tablename__ = "extracoes"

    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))
    valor: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class DbCache:
    def __init__(self, session: Session) -> None:
        self.s = session

    def get(self, chave: str) -> str | None:
        row = self.s.get(Extracao, chave)
        return row.valor if row else None

    def set(self, chave: str, tipo: str, valor: str) -> None:
        self.s.merge(Extracao(chave=chave, tipo=tipo, valor=valor))
        self.s.commit()


_engine = None
_SessionLocal = None


def _url_psycopg(url: str) -> str:
    """Aceita a URL no formato do Render/Heroku (postgres://) e usa o driver psycopg 3."""
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    return url


def engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(_url_psycopg(get_settings().database_url), pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def criar_tabelas() -> None:
    eng = engine()
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(eng)


def get_session():
    engine()
    with _SessionLocal() as s:
        yield s


__all__ = ["Base", "Edital", "Candidato", "TrechoEdital", "Extracao", "DbCache", "criar_tabelas", "get_session", "select"]
