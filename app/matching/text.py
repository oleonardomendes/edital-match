"""Normalização de texto e equivalências usadas na comparação de requisitos."""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "nos", "nas", "com", "para", "por", "um", "uma", "ou", "ao", "aos", "the",
    "of", "and", "in", "area", "areas", "atuacao", "experiencia", "conhecimento",
    "conhecimentos", "solida", "comprovada", "minimo", "minima",
}

# Grafias diferentes para a mesma coisa. A chave e os valores já normalizados.
EQUIVALENCIAS: dict[str, set[str]] = {
    "pmp": {"project management professional", "pmp pmi"},
    "scrum master": {"psm", "psm i", "professional scrum master", "csm", "certified scrummaster"},
    "itil": {"itil foundation", "itil v4", "itil 4 foundation", "itil v3"},
    "cobit": {"cobit 5", "cobit 2019"},
    "oracle": {"oracle database", "oracle db"},
    "sql server": {"mssql", "microsoft sql server", "t sql", "tsql"},
    "postgresql": {"postgres", "postgre sql"},
    "javascript": {"js", "ecmascript"},
    "typescript": {"ts"},
    "c#": {"c sharp", "csharp"},
    ".net": {"dotnet", "asp net", "asp.net"},
    "aws": {"amazon web services"},
    "azure": {"microsoft azure"},
    "gcp": {"google cloud", "google cloud platform"},
    "power bi": {"powerbi"},
    "ciencia da computacao": {"computer science", "bacharelado em ciencia da computacao"},
    "sistemas de informacao": {"information systems"},
    "engenharia de software": {"software engineering"},
    "analise e desenvolvimento de sistemas": {"ads", "tecnologia em analise e desenvolvimento de sistemas"},
}

_CANON: dict[str, str] = {}
for canon, variantes in EQUIVALENCIAS.items():
    _CANON[canon] = canon
    for v in variantes:
        _CANON[v] = canon


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e sem pontuação (preserva # e . de C# e .NET)."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9#.+ ]", " ", texto)
    texto = re.sub(r"(?<![a-z0-9])\.(?![a-z0-9])", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def canonico(texto: str) -> str:
    n = normalizar(texto)
    return _CANON.get(n, n)


# Siglas que valem por expressões inteiras na comparação por palavras.
SIGLAS = {
    "ti": "tecnologia da informacao",
    "si": "sistemas de informacao",
    "ads": "analise e desenvolvimento de sistemas",
    "bd": "banco de dados",
}


def tokens(texto: str) -> set[str]:
    palavras = []
    for t in normalizar(texto).split():
        palavras.extend(SIGLAS.get(t, t).split())
    return {_radical(t) for t in palavras if t not in STOPWORDS and len(t) > 1}


def _radical(t: str) -> str:
    """Radical simples para português: reduz plural e alguns sufixos comuns."""
    for suf in ("coes", "cao", "mente", "idade", "istas", "ista", "ores", "or", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def mesmo_item(a: str, b: str, limiar: int = 88) -> bool:
    """Compara nomes curtos (certificações, tecnologias, cursos)."""
    ca, cb = canonico(a), canonico(b)
    if ca == cb:
        return True
    if not ca or not cb:
        return False
    curto, longo = sorted((ca, cb), key=len)
    if len(curto) <= 4:
        # Siglas: só valem como palavra inteira ("pmp" em "pmp project management
        # professional"), para que "java" não case com "javascript".
        return f" {curto} " in f" {longo} "
    if f" {curto} " in f" {longo} ":
        return True
    return fuzz.token_set_ratio(ca, cb) >= limiar


def contem_termo(texto: str, termo: str) -> bool:
    """Verifica se o termo aparece no texto como palavra ou expressão inteira."""
    t = canonico(termo)
    alvo = f" {normalizar(texto)} "
    candidatos = {t} | {k for k, v in _CANON.items() if v == t}
    return any(f" {c} " in alvo for c in candidatos)
