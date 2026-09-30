from dataclasses import dataclass


@dataclass(frozen=True)
class Pergunta:
    id: int
    categoria: str
    pergunta: str
    alternativas: tuple[str, ...]
    correta: int
    explicacao: str


# Cópia provisória das perguntas de src/data/perguntas.js. Índices começam em zero.
PERGUNTAS = (
    Pergunta(1, "geral", "Qual é a capital do Brasil?", ("São Paulo", "Rio de Janeiro", "Brasília", "Salvador"), 2, 'Brasília é a capital federal do Brasil e sede dos principais órgãos do governo federal.'),
    Pergunta(2, "geral", "Qual é o maior planeta do Sistema Solar?", ("Terra", "Marte", "Júpiter", "Saturno"), 2, 'Júpiter é o maior planeta do Sistema Solar, superando todos os demais em tamanho e massa.'),
    Pergunta(3, "geral", "Em qual continente fica o Egito?", ("África", "Ásia", "Europa", "América"), 0, 'O Egito está localizado principalmente no nordeste da África, embora a Península do Sinai pertença geograficamente à Ásia.'),
    Pergunta(4, "geral", "Qual oceano banha a costa leste do Brasil?", ("Pacífico", "Atlântico", "Índico", "Ártico"), 1, 'O litoral brasileiro está voltado para o Oceano Atlântico, que se estende entre as Américas, a Europa e a África.'),
    Pergunta(5, "geral", "Quantos lados possui um hexágono?", ("Cinco", "Seis", "Sete", "Oito"), 1, 'Um hexágono é um polígono formado por seis lados e seis vértices.'),
    Pergunta(6, "tecnologia", "Qual linguagem é executada nativamente pelos navegadores?", ("Python", "JavaScript", "Java", "C#"), 1, 'JavaScript é executado diretamente pelos navegadores e permite adicionar lógica e interatividade às páginas web.'),
    Pergunta(7, "tecnologia", "Qual tecnologia é usada para estruturar uma página web?", ("HTML", "CSS", "SQL", "Git"), 0, 'HTML define a estrutura e o conteúdo de uma página, organizando elementos como títulos, textos, imagens e links.'),
    Pergunta(8, "tecnologia", "Qual tecnologia é usada principalmente para estilizar páginas web?", ("React", "Python", "CSS", "Node.js"), 2, 'CSS controla a apresentação visual de páginas web, incluindo cores, tamanhos, espaçamento e posicionamento dos elementos.'),
    Pergunta(9, "tecnologia", "Qual ferramenta é usada para controle de versão?", ("Git", "Vite", "Chrome", "PostgreSQL"), 0, 'Git registra alterações nos arquivos ao longo do desenvolvimento e permite trabalhar com diferentes versões de um projeto.'),
    Pergunta(10, "tecnologia", "Qual destes é um banco de dados relacional?", ("React", "PostgreSQL", "Vite", "CSS"), 1, 'PostgreSQL é um sistema gerenciador de banco de dados relacional que organiza dados principalmente em tabelas relacionadas.'),
    Pergunta(11, "matematica", "Quanto é 8 × 7?", ("48", "54", "56", "64"), 2, 'Multiplicando 8 por 7, temos 8 × 7 = 56.'),
    Pergunta(12, "matematica", "Quanto é 144 ÷ 12?", ("10", "11", "12", "14"), 2, 'Dividindo 144 em 12 partes iguais, obtemos 12, pois 12 × 12 = 144.'),
    Pergunta(13, "matematica", "Quanto é 15 + 27?", ("40", "41", "42", "43"), 2, 'Somando 15 e 27, temos 15 + 27 = 42.'),
    Pergunta(14, "matematica", "Quanto é 9²?", ("18", "72", "81", "90"), 2, 'Elevar 9 ao quadrado significa multiplicá-lo por ele mesmo: 9 × 9 = 81.'),
    Pergunta(15, "matematica", "Qual é a metade de 250?", ("100", "115", "125", "150"), 2, 'Para encontrar a metade, dividimos por 2: 250 ÷ 2 = 125.'),
)
