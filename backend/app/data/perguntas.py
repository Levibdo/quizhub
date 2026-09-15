from dataclasses import dataclass


@dataclass(frozen=True)
class Pergunta:
    id: int
    categoria: str
    pergunta: str
    alternativas: tuple[str, ...]
    correta: int


# Cópia provisória das perguntas de src/data/perguntas.js. Índices começam em zero.
PERGUNTAS = (
    Pergunta(1, "geral", "Qual é a capital do Brasil?", ("São Paulo", "Rio de Janeiro", "Brasília", "Salvador"), 2),
    Pergunta(2, "geral", "Qual é o maior planeta do Sistema Solar?", ("Terra", "Marte", "Júpiter", "Saturno"), 2),
    Pergunta(3, "geral", "Em qual continente fica o Egito?", ("África", "Ásia", "Europa", "América"), 0),
    Pergunta(4, "geral", "Qual oceano banha a costa leste do Brasil?", ("Pacífico", "Atlântico", "Índico", "Ártico"), 1),
    Pergunta(5, "geral", "Quantos lados possui um hexágono?", ("Cinco", "Seis", "Sete", "Oito"), 1),
    Pergunta(6, "tecnologia", "Qual linguagem é executada nativamente pelos navegadores?", ("Python", "JavaScript", "Java", "C#"), 1),
    Pergunta(7, "tecnologia", "Qual tecnologia é usada para estruturar uma página web?", ("HTML", "CSS", "SQL", "Git"), 0),
    Pergunta(8, "tecnologia", "Qual tecnologia é usada principalmente para estilizar páginas web?", ("React", "Python", "CSS", "Node.js"), 2),
    Pergunta(9, "tecnologia", "Qual ferramenta é usada para controle de versão?", ("Git", "Vite", "Chrome", "PostgreSQL"), 0),
    Pergunta(10, "tecnologia", "Qual destes é um banco de dados relacional?", ("React", "PostgreSQL", "Vite", "CSS"), 1),
    Pergunta(11, "matematica", "Quanto é 8 × 7?", ("48", "54", "56", "64"), 2),
    Pergunta(12, "matematica", "Quanto é 144 ÷ 12?", ("10", "11", "12", "14"), 2),
    Pergunta(13, "matematica", "Quanto é 15 + 27?", ("40", "41", "42", "43"), 2),
    Pergunta(14, "matematica", "Quanto é 9²?", ("18", "72", "81", "90"), 2),
    Pergunta(15, "matematica", "Qual é a metade de 250?", ("100", "115", "125", "150"), 2),
)
