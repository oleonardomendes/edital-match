"""Currículos fictícios usados no exemplo e na avaliação.

Cada candidato foi escrito para testar um caso real de licitação. O campo
``caso`` explica o que ele testa. Todos os nomes, empresas e dados são inventados.
"""

CANDIDATOS = [
    {
        "arquivo": "cv_mariana_duarte.pdf",
        "caso": "Gerente de projetos completa: atende tudo, inclusive os desejáveis.",
        "resumo": "Gerente de projetos de TI com foco em sistemas para o setor público e equipes ágeis.",
        "perfil": {
            "nome": "Mariana Duarte Lima",
            "formacoes": [
                {"nivel": "graduacao", "curso": "Ciência da Computação", "instituicao": "Universidade Estadual do Vale", "concluida": True, "ano_conclusao": 2011},
                {"nivel": "pos_graduacao", "curso": "MBA em Gestão de Projetos", "instituicao": "Faculdade Horizonte", "concluida": True, "ano_conclusao": 2016},
            ],
            "experiencias": [
                {"cargo": "Desenvolvedora .NET", "empresa": "Codex Softwares", "inicio": "2012-02-01", "fim": "2016-12-01",
                 "descricao": "Desenvolvimento de sistemas web em C# e SQL Server.", "tecnologias": ["C#", ".NET", "SQL Server"]},
                {"cargo": "Gerente de Projetos de TI", "empresa": "Nexo Sistemas", "inicio": "2017-01-01", "fim": None,
                 "descricao": "Gestão de projetos de tecnologia da informação para prefeituras, com equipes de até 15 pessoas, cronograma, riscos e orçamento.",
                 "tecnologias": ["Jira", "MS Project"]},
            ],
            "certificacoes": [
                {"nome": "PMP - Project Management Professional", "emissor": "PMI", "ano": 2019},
                {"nome": "Professional Scrum Master I (PSM I)", "emissor": "Scrum.org", "ano": 2021},
            ],
            "competencias": ["Gestão de riscos", "Scrum", "Jira", "MS Project"],
        },
    },
    {
        "arquivo": "cv_rafael_teixeira.pdf",
        "caso": "Experiência e PMP de sobra, mas a graduação é em Administração: inapto pela formação.",
        "resumo": "Coordenador de projetos de TI com mais de dez anos em implantação de ERPs.",
        "perfil": {
            "nome": "Rafael Teixeira Nunes",
            "formacoes": [
                {"nivel": "graduacao", "curso": "Administração de Empresas", "instituicao": "Faculdade Central", "concluida": True, "ano_conclusao": 2012},
                {"nivel": "pos_graduacao", "curso": "MBA em Gerenciamento de Projetos", "instituicao": "Escola de Negócios Atlântica", "concluida": True, "ano_conclusao": 2015},
            ],
            "experiencias": [
                {"cargo": "Coordenador de Projetos de TI", "empresa": "Integra ERP", "inicio": "2015-03-01", "fim": None,
                 "descricao": "Gestão de projetos de tecnologia da informação na implantação de ERP em clientes de médio porte.",
                 "tecnologias": ["MS Project"]},
            ],
            "certificacoes": [{"nome": "PMP", "emissor": "PMI", "ano": 2017}],
            "competencias": ["MS Project", "Gestão de contratos"],
        },
    },
    {
        "arquivo": "cv_camila_rocha.pdf",
        "caso": "Tem CAPM, que é outra certificação do PMI e não substitui o PMP exigido.",
        "resumo": "Gerente de projetos de TI em consultoria, com certificação ágil.",
        "perfil": {
            "nome": "Camila Rocha Prado",
            "formacoes": [
                {"nivel": "graduacao", "curso": "Sistemas de Informação", "instituicao": "Centro Universitário Paulista", "concluida": True, "ano_conclusao": 2014},
            ],
            "experiencias": [
                {"cargo": "Analista de Requisitos", "empresa": "Prisma Consultoria", "inicio": "2014-06-01", "fim": "2018-12-01",
                 "descricao": "Levantamento de requisitos e modelagem de processos.", "tecnologias": ["BPMN"]},
                {"cargo": "Gerente de Projetos de TI", "empresa": "Prisma Consultoria", "inicio": "2019-01-01", "fim": None,
                 "descricao": "Gestão de projetos de tecnologia da informação com métodos ágeis.", "tecnologias": ["Jira"]},
            ],
            "certificacoes": [
                {"nome": "CAPM - Certified Associate in Project Management", "emissor": "PMI", "ano": 2018},
                {"nome": "Certified ScrumMaster (CSM)", "emissor": "Scrum Alliance", "ano": 2020},
            ],
            "competencias": ["Jira", "Scrum", "Kanban"],
        },
    },
    {
        "arquivo": "cv_bruno_sales.pdf",
        "caso": "Analista sênior completo: atende todos os obrigatórios e desejáveis.",
        "resumo": "Analista de sistemas com experiência em sistemas de gestão pública em Java e Oracle.",
        "perfil": {
            "nome": "Bruno Henrique Sales",
            "formacoes": [
                {"nivel": "graduacao", "curso": "Engenharia de Software", "instituicao": "Universidade Federal do Interior", "concluida": True, "ano_conclusao": 2014},
            ],
            "experiencias": [
                {"cargo": "Desenvolvedor Java", "empresa": "GovTec Sistemas", "inicio": "2015-01-01", "fim": "2019-06-01",
                 "descricao": "Desenvolvimento de sistemas de arrecadação municipal com Java, Oracle e PL/SQL.",
                 "tecnologias": ["Java", "Oracle", "PL/SQL"]},
                {"cargo": "Analista de Sistemas", "empresa": "Nexo Sistemas", "inicio": "2019-07-01", "fim": None,
                 "descricao": "Desenvolvimento de sistemas e integração por APIs REST entre os módulos de RH e financeiro.",
                 "tecnologias": ["Java", "Spring Boot", "APIs REST", "Oracle"]},
            ],
            "certificacoes": [{"nome": "ITIL 4 Foundation", "emissor": "AXELOS", "ano": 2022}],
            "competencias": ["Java", "Oracle", "PL/SQL", "APIs REST", "Git"],
        },
    },
    {
        "arquivo": "cv_juliana_matos.pdf",
        "caso": "Tecnóloga em ADS: apta nos obrigatórios, mas sem os desejáveis Java e ITIL.",
        "resumo": "Analista de sistemas com passagem por PHP e hoje focada em Oracle.",
        "perfil": {
            "nome": "Juliana Matos Ferreira",
            "formacoes": [
                {"nivel": "graduacao", "curso": "Tecnologia em Análise e Desenvolvimento de Sistemas", "instituicao": "Fatec Vale Verde", "concluida": True, "ano_conclusao": 2015},
            ],
            "experiencias": [
                {"cargo": "Desenvolvedora PHP", "empresa": "Web Ágil", "inicio": "2016-02-01", "fim": "2020-01-01",
                 "descricao": "Desenvolvimento de sistemas web em PHP com MySQL.", "tecnologias": ["PHP", "MySQL"]},
                {"cargo": "Analista de Sistemas", "empresa": "Cooperativa Agro Norte", "inicio": "2020-02-01", "fim": None,
                 "descricao": "Desenvolvimento de sistemas internos com banco Oracle, rotinas em PL/SQL e APIs REST.",
                 "tecnologias": ["Oracle", "PL/SQL", "APIs REST"]},
            ],
            "certificacoes": [],
            "competencias": ["Oracle", "PL/SQL", "PHP"],
        },
    },
    {
        "arquivo": "cv_diego_carvalho.pdf",
        "caso": "Experiência técnica forte, mas a graduação ainda está em andamento: inapto.",
        "resumo": "Desenvolvedor Java e Oracle há mais de dez anos, concluindo a graduação.",
        "perfil": {
            "nome": "Diego Carvalho Pinto",
            "formacoes": [
                {"nivel": "graduacao", "curso": "Ciência da Computação", "instituicao": "Universidade Estadual do Vale", "concluida": False, "ano_conclusao": None},
                {"nivel": "tecnico", "curso": "Técnico em Informática", "instituicao": "ETEC Vale Verde", "concluida": True, "ano_conclusao": 2012},
            ],
            "experiencias": [
                {"cargo": "Desenvolvedor de Sistemas", "empresa": "Banco Regional do Vale", "inicio": "2014-03-01", "fim": None,
                 "descricao": "Desenvolvimento de sistemas bancários em Java com Oracle e PL/SQL.",
                 "tecnologias": ["Java", "Oracle", "PL/SQL"]},
            ],
            "certificacoes": [],
            "competencias": ["Java", "Oracle", "PL/SQL"],
        },
    },
    {
        "arquivo": "cv_patricia_gomes.pdf",
        "caso": "Somando os períodos dá mais de 8 anos, mas dois empregos foram simultâneos. Contando uma vez só, ficam 5,7 anos: inapta.",
        "resumo": "Desenvolvedora com atuação em empresa e projetos freelance ao mesmo tempo.",
        "perfil": {
            "nome": "Patrícia Gomes Alencar",
            "formacoes": [
                {"nivel": "graduacao", "curso": "Sistemas de Informação", "instituicao": "Centro Universitário Paulista", "concluida": True, "ano_conclusao": 2019},
            ],
            "experiencias": [
                {"cargo": "Desenvolvedora de Sistemas", "empresa": "Soluções Lumen", "inicio": "2020-01-01", "fim": "2023-12-01",
                 "descricao": "Desenvolvimento de sistemas em Java com Oracle e PL/SQL.", "tecnologias": ["Java", "Oracle", "PL/SQL"]},
                {"cargo": "Desenvolvedora de Sistemas (freelancer)", "empresa": None, "inicio": "2021-01-01", "fim": "2023-06-01",
                 "descricao": "Desenvolvimento de sistemas sob demanda para pequenas empresas.", "tecnologias": ["Java"]},
                {"cargo": "Analista de Sistemas", "empresa": "Fintech Orbe", "inicio": "2025-01-01", "fim": None,
                 "descricao": "Desenvolvimento de sistemas e integrações por APIs REST.", "tecnologias": ["Java", "APIs REST", "Oracle"]},
            ],
            "certificacoes": [],
            "competencias": ["Java", "Oracle", "PL/SQL", "APIs REST"],
        },
    },
    {
        "arquivo": "cv_thiago_moreira.pdf",
        "caso": "Fora da área: 'gerente' em restaurante não conta como gestão de projetos de TI.",
        "resumo": "Gerente de restaurante buscando transição de carreira.",
        "perfil": {
            "nome": "Thiago Moreira Campos",
            "formacoes": [
                {"nivel": "graduacao", "curso": "Gastronomia", "instituicao": "Faculdade Sabores", "concluida": True, "ano_conclusao": 2010},
            ],
            "experiencias": [
                {"cargo": "Gerente de Restaurante", "empresa": "Cantina Bella Vista", "inicio": "2011-05-01", "fim": None,
                 "descricao": "Gestão de equipe de salão e cozinha, controle de estoque e atendimento ao cliente.", "tecnologias": []},
            ],
            "certificacoes": [],
            "competencias": ["Gestão de equipes", "Excel"],
        },
    },
]
