PROMPT_EDITAL = """Você recebe o texto de um edital de licitação ou termo de referência.
Extraia os perfis profissionais exigidos da equipe técnica e os requisitos de cada perfil.

Regras:
- Use apenas o que está escrito no edital. Não invente requisitos.
- Um requisito é obrigatório quando o edital usa termos como "exigido", "obrigatório",
  "mínimo", "deverá possuir" ou o coloca como condição de habilitação. Requisitos que só
  somam pontos ou aparecem como "desejável" têm obrigatorio=false.
- Pesos: requisitos obrigatórios têm peso 3. Requisitos desejáveis usam os pontos que o
  edital atribui; sem pontuação definida, peso 1.
- Converta tempo de experiência para anos (ex.: 24 meses = 2).
- Em texto_original, copie o trecho do edital que gerou o requisito.
- O texto pode vir em trechos marcados com [p. N · seção]. Em pagina, informe o N do
  trecho de onde saiu cada requisito. Sem marcação, deixe pagina vazia.
- Em regras_equipe, registre o que o edital diz sobre quando e como a equipe é comprovada
  (na proposta, na habilitação ou na assinatura do contrato), substituição de profissionais
  e tipo de vínculo aceito (CLT, contrato de prestação de serviço, declaração de contratação
  futura). Só o que estiver escrito.
- Separe certificações (PMP, ITIL, Scrum) de competências técnicas (Java, Oracle, SQL).
- Um requisito com "X e Y" exige as duas coisas: crie um requisito para X e outro para Y
  (ex.: "Oracle e PL/SQL" vira duas competências). Um requisito com "X ou Y" aceita qualquer
  uma: crie um só requisito com Y em alternativas.
- Em formação, liste em areas todos os cursos citados e também a área geral, quando houver
  (ex.: "qualquer área de TI, como Ciência da Computação ou Sistemas de Informação" vira
  ["Tecnologia da Informação", "Ciência da Computação", "Sistemas de Informação"]).
"""

PROMPT_CARGOS = """Você recebe trechos de um edital de licitação ou termo de referência, marcados com [p. N · seção].
Liste os perfis profissionais que o edital exige ou descreve para a equipe técnica.

Regras:
- Use apenas o que está escrito. Não invente cargos.
- Cada nível conta como um perfil diferente (ex.: "Desenvolvedor Júnior Java" e "Desenvolvedor
  Sênior Java"). Use o nome como o edital escreve.
- Em pagina, informe o N do trecho onde o perfil é descrito.
- Em regras_equipe, registre o que o edital diz sobre quando e como a equipe é comprovada
  (na proposta, na habilitação ou após a assinatura do contrato), substituição de profissionais
  e vínculo aceito. Só o que estiver escrito, com a página.
- Tabelas de PDF podem vir com as colunas misturadas. Junte as partes com cuidado.
"""

PROMPT_PERFIL = """Você recebe trechos de um edital de licitação, marcados com [p. N · seção].
Extraia os requisitos de UM perfil profissional: {cargo}.

Regras:
- Use apenas o que o edital exige para este perfil. Ignore requisitos de outros perfis que
  apareçam nos mesmos trechos. Se os trechos não descrevem este perfil, devolva as listas vazias.
- Requisito obrigatório: o edital usa "exigido", "obrigatório", "mínimo", "deverá possuir".
  Desejável: só soma pontos ou é chamado de desejável.
- Pesos: obrigatórios peso 3; desejáveis usam os pontos do edital, ou 1.
- Converta tempo de experiência para anos.
- Formação com alternativas ("curso de TI, ou qualquer superior com pós em TI") é UM requisito:
  use o menor nível aceito e liste as áreas.
- "X e Y" exige os dois (dois requisitos); "X ou Y" aceita qualquer um (um requisito com alternativas).
- Separe certificações de competências técnicas. Habilidades comportamentais (comunicação,
  proatividade) não são competências técnicas: deixe de fora.
- Em texto_original, copie o trecho do edital. Em pagina, o N do trecho.
"""

PROMPT_CV = """Você recebe o texto de um currículo. Extraia os dados estruturados do candidato.

Regras:
- Use apenas o que está escrito. Não deduza certificações nem competências.
- Datas no formato AAAA-MM-DD. Quando só houver mês e ano, use o dia 01. Quando só houver
  o ano, use 01 de janeiro. Deixe fim vazio quando for o emprego atual.
- Em tecnologias, liste as ferramentas e linguagens citadas em cada experiência.
- Em nivel, use: medio, tecnico, graduacao, pos_graduacao, mestrado ou doutorado.
  MBA e especialização contam como pos_graduacao. Tecnólogo conta como graduacao.
- Marque concluida=false para cursos em andamento ou trancados.
"""
