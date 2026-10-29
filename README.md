# Edital Match

Cruza os requisitos da equipe técnica de um edital de licitação com uma base de currículos e gera, para cada cargo, um ranking de profissionais com **score, situação (apto ou inapto) e a evidência de cada critério**.

🔗 **Demo:** https://edital-match.onrender.com (clique em **Usar o exemplo fictício**). Está no plano gratuito do Render: depois de um tempo sem acesso, a primeira abertura leva cerca de 1 minuto.

![Ranking do cargo Analista de Sistemas Sênior](docs/ranking.png)

## O problema

Em licitações de serviços de TI, a empresa precisa comprovar que tem profissionais com o perfil exigido no edital: formação, anos de experiência em uma área, certificações e conhecimentos específicos. Montar essa equipe significa ler o edital, entender cada exigência e conferir currículo por currículo. Na empresa onde fiz a primeira versão disso, o processo levava **dias de trabalho manual a cada edital**.

O Edital Match faz essa triagem automaticamente. Esta é uma reconstrução open source, com dados fictícios, de uma automação que eu construí para um time de RH.

## Como funciona

```
Edital (PDF) ──► LLM extrai os perfis e requisitos ──► revisão humana (opcional)
                                                              │
Currículos ────► LLM extrai formação, experiências,           ▼
(PDF/DOCX)       certificações e competências ──► Motor de regras ──► Ranking explicável
                        │
                        └──► embedding no pgvector ──► busca semântica no banco de currículos
```

**Cada edital tem suas regras, e uma pessoa confirma antes do ranking.** A IA extrai os requisitos e mostra, ao lado de cada um, o trecho do edital de onde ele saiu. Quem usa confere, muda o que é exigido ou desejável, ajusta pesos, adiciona ou remove requisitos e salva. O ranking é recalculado na hora.

![Revisão dos requisitos com o trecho do edital](docs/revisao.png)

**A IA extrai, as regras decidem.** O LLM só transforma texto em dados estruturados (validados com Pydantic). A decisão de apto ou inapto e o score saem de um motor de regras determinístico. Em licitação, cada decisão precisa ser justificável: a mesma entrada sempre gera o mesmo resultado, e cada critério mostra o trecho do currículo que o comprova.

O motor cuida dos detalhes que costumam derrubar uma habilitação:

| Regra | Exemplo |
|---|---|
| Períodos de experiência simultâneos contam uma vez só, como os editais costumam exigir | Dois empregos ao mesmo tempo de 2021 a 2023 não somam 4 anos |
| Graduação em andamento não atende requisito de graduação | Conta como parcial e torna o candidato inapto se for exigida |
| Equivalência entre certificações | ITIL 4 Foundation atende ITIL Foundation; PSM atende Scrum Master |
| Siglas parecidas não são confundidas | CAPM não substitui PMP; Java não é JavaScript |
| Experiência precisa ser na área pedida | "Gerente de restaurante" não conta como gestão de projetos de TI |
| Requisitos "X ou Y" | Jira **ou** MS Project |

Requisitos exigidos eliminam quem não atende. Requisitos desejáveis somam pontos com o peso que o edital define.

## Avaliação

Para medir o motor, escrevi um edital fictício com 2 cargos e 8 currículos que testam casos difíceis, e classifiquei cada candidato à mão antes de rodar o sistema ([gabarito](eval/gabarito.json), [casos](samples/candidatos.py)).

```bash
python -m eval.run_eval
```

| Métrica | Resultado |
|---|---|
| Acerto apto/inapto (16 decisões) | 100% |
| Acerto do motivo de inaptidão | 100% |
| NDCG da ordem dos aptos | 1,0 |

A tabela acima usa os requisitos e perfis do gabarito, então mede só o motor de regras.

### Com extração por IA (cadeia completa)

O modo `--modo llm` lê os PDFs, extrai tudo com o LLM e compara a extração e as decisões com o mesmo gabarito. Rodei com `openai/gpt-oss-120b` no Groq:

| Métrica | 1ª rodada | 2ª rodada (prompt ajustado) |
|---|---|---|
| Requisitos do edital encontrados | 11 de 12 | 12 de 12 |
| Obrigatório/desejável correto | 11 de 11 | 12 de 12 |
| Currículos (nomes, experiências, anos, certificações, formações) | sem erros | sem erros |
| Acerto apto/inapto (16 decisões) | 93,8% | 100% |
| Acerto do motivo de inaptidão | 92,3% | 100% |
| NDCG da ordem dos aptos | 0,5 | 1,0 |

Na 1ª rodada o modelo juntou "Oracle e PL/SQL" num requisito só e listou áreas de formação incompletas, o que deixou uma candidata apta como inapta. Ajustei duas regras no [prompt](app/extraction/prompts.py) e a 2ª rodada acertou tudo.

**Limitação:** o conjunto é pequeno, e tanto as regras de comparação quanto o prompt foram ajustados olhando para ele. Esses números medem consistência, não generalização. O próximo passo é ampliar o gabarito com editais reais.

## Stack

| Camada | Tecnologia |
|---|---|
| API | FastAPI, Pydantic |
| Banco | PostgreSQL + pgvector (SQLAlchemy) |
| Extração | Claude (Anthropic) com tool use, ou qualquer API compatível com OpenAI, como Groq |
| Busca semântica | Embeddings com fastembed (local, multilíngue) ou OpenAI |
| Documentos | pypdf, python-docx |
| Testes e CI | pytest, GitHub Actions com Postgres + pgvector |
| Deploy | Docker e docker-compose |

Desenvolvido com apoio do Claude Code.

## Como rodar

**Com Docker:**

```bash
cp .env.example .env
docker compose up --build
```

Abra http://localhost:8000 e clique em **Usar o exemplo fictício**. O modo demo funciona sem chave de API, porque as extrações dos documentos de exemplo já estão em cache.

**Para analisar seus próprios documentos**, configure o LLM no `.env`:

```env
LLM_PROVIDER=anthropic
LLM_API_KEY=sua-chave
EMBEDDING_PROVIDER=fastembed   # requer: pip install fastembed
```

**Sem Docker:**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload       # precisa de um Postgres com pgvector em DATABASE_URL
pytest                              # testes de API rodam se TEST_DATABASE_URL estiver definida
```

## API

| Método | Rota | O que faz |
|---|---|---|
| POST | `/api/editais` | Envia o edital e devolve os perfis e requisitos extraídos |
| PUT | `/api/editais/{id}/requisitos` | Salva a revisão dos requisitos (exigido ou desejável, pesos, itens) |
| POST | `/api/candidatos` | Envia um ou mais currículos |
| GET | `/api/editais/{id}/ranking?cargo=` | Ranking explicável por cargo |
| GET | `/api/candidatos/busca?q=` | Busca semântica no banco de currículos (pgvector) |
| POST | `/api/exemplo` | Carrega o edital e os currículos fictícios |

A documentação interativa fica em `/docs`.

## Estrutura

```
app/
├── extraction/   # leitura de PDF/DOCX, prompts, clientes de LLM e cache de extração
├── matching/     # motor de regras, similaridade de texto e embeddings
├── main.py       # API
└── static/       # interface web
eval/             # gabarito e script de avaliação
samples/          # edital e currículos fictícios (fontes e PDFs)
tests/            # testes do motor, da avaliação e da API
```

## Próximos passos

- Ampliar o gabarito com editais públicos reais e medir a extração por LLM
- Exportar a equipe escolhida em planilha no formato pedido pelo edital
- Ler PDFs escaneados com OCR

## Autor

**Leonardo Mendes da Silva** · [LinkedIn](https://www.linkedin.com/in/leonardo-mendes-418202181) · [GitHub](https://github.com/oleonardomendes)

Todos os nomes, empresas e órgãos dos exemplos são fictícios.
