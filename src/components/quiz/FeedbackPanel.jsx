const LETRAS = ['A', 'B', 'C', 'D']

function FeedbackPanel({
  timeout,
  correta,
  alternativaCorreta,
  alternativas,
  explicacao,
  pontos,
  ultimaPergunta,
  carregandoAvanco,
  onAvancar,
}) {
  const tipo = timeout ? 'timeout' : correta ? 'acerto' : 'erro'
  const conteudo = {
    acerto: {
      metadado: 'Resultado // Acerto',
      titulo: 'Resposta correta',
      descricao: null,
    },
    erro: {
      metadado: 'Resultado // Erro',
      titulo: 'Resposta incorreta',
      descricao: null,
    },
    timeout: {
      metadado: 'Resultado // Tempo esgotado',
      titulo: 'Tempo esgotado',
      descricao: 'Nenhuma resposta foi registrada.',
    },
  }[tipo]
  const letraCorreta = LETRAS[alternativaCorreta]
  const textoCorreto = alternativas[alternativaCorreta]
  const respostaCorreta = [letraCorreta, textoCorreto].filter(Boolean).join(' — ')

  return (
    <section className={`feedback-panel feedback-panel--${tipo}`} aria-live="polite">
      <header className="feedback-panel__header">
        <span className="feedback-panel__meta">{conteudo.metadado}</span>
        <h2>{conteudo.titulo}</h2>
        {conteudo.descricao && <p>{conteudo.descricao}</p>}
      </header>

      <div className="feedback-panel__answer">
        <span className="feedback-panel__label">Resposta correta</span>
        <strong>{respostaCorreta}</strong>
      </div>

      <div className="feedback-panel__explanation">
        <span className="feedback-panel__label">Explicação</span>
        <p>{explicacao}</p>
      </div>

      <footer className="feedback-panel__footer">
        <div className="feedback-panel__points">
          <span className="feedback-panel__label">Pontos recebidos</span>
          <strong>+{pontos} pontos</strong>
        </div>
        <button
          className="proxima-pergunta"
          type="button"
          onClick={onAvancar}
          disabled={carregandoAvanco}
        >
          {carregandoAvanco
            ? 'Preparando próxima...'
            : ultimaPergunta ? 'Ver resultado →' : 'Próxima pergunta →'}
        </button>
      </footer>
    </section>
  )
}

export default FeedbackPanel
