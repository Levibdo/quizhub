from uuid import UUID


MODO_QUIZ_CLASSICO = "QUIZ_CLASSICO"
MODO_NEM_A_PATO = "NEM_A_PATO"
ORIGEM_OFICIAL = "OFICIAL"
ORIGEM_USUARIO = "USUARIO"

MODOS_CONTEUDO = (MODO_QUIZ_CLASSICO, MODO_NEM_A_PATO)
ORIGENS_CONTEUDO = (ORIGEM_OFICIAL, ORIGEM_USUARIO)

LIMITE_CATEGORIAS_USUARIO_POR_MODO = 10
LIMITE_PERGUNTAS_USUARIO_POR_MODO = 200

CATEGORIAS_OFICIAIS = {
    MODO_QUIZ_CLASSICO: {
        "geral": UUID("40f40d1f-fa4a-5cc0-9a2f-910bfbf4b4cb"),
        "tecnologia": UUID("e534376c-ec51-5304-a42c-cac8d6e34bba"),
        "matematica": UUID("bb9a1050-b3d9-5c42-9cdd-d3747548fc66"),
        "entretenimento": UUID("2a01b416-ae0c-53b4-8081-b5f33230048c"),
    },
    MODO_NEM_A_PATO: {
        "geral": UUID("6cb33fc5-8545-55df-8c46-2e85fc67fe5c"),
        "tecnologia": UUID("968d29fc-c00f-50c5-9f71-e2d1c53a603d"),
        "matematica": UUID("57036809-591b-54a0-a1ea-b2b815ffea01"),
        "entretenimento": UUID("6feed2ed-5be2-58a8-ad78-37077af2cfca"),
    },
}
