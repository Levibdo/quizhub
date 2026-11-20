import { formatarPalpite } from './formatters'

function NemAPatoRoundResult({
  carregando,
  jogadorAtivo,
  partida,
  rodada,
  aoIniciarProximaRodada,
}) {
  return (
    <section className="np-round np-result" aria-labelledby="np-result-title">
      <p className="np-round__counter">Rodada {rodada.numero} de {partida.total_rodadas}</p>
      <h3 id="np-result-title">RESULTADO</h3>
      <p className="np-round__question">{rodada.pergunta?.enunciado}</p>
      <div className="np-result__answer">
        <span>Resposta correta</span>
        <strong>{formatarPalpite(rodada.pergunta?.resposta_numerica, rodada.pergunta?.unidade)}</strong>
      </div>
      {rodada.resultado_desafio && (
        <>
          <p>Último palpite: <strong>{rodada.resultado_desafio.palpite_desafiado.jogador.nome} — {formatarPalpite(rodada.resultado_desafio.palpite_desafiado.valor, rodada.pergunta?.unidade)}</strong></p>
          <p><strong>{rodada.resultado_desafio.desafiante.nome}</strong> disse “Nem a Pato!”</p>
          <p className="np-result__penalty"><strong>{rodada.resultado_desafio.jogador_penalizado.nome}</strong> recebeu 1 pato.</p>
        </>
      )}
      {rodada.resultado_timeout && (
        <>
          <h4>TEMPO ESGOTADO</h4>
          {rodada.resultado_timeout.ultimo_palpite ? (
            <>
              <p>Maior palpite: <strong>{rodada.resultado_timeout.autor_protegido.nome} — {formatarPalpite(rodada.resultado_timeout.ultimo_palpite.valor, rodada.pergunta?.unidade)}</strong></p>
              <p><strong>{rodada.resultado_timeout.autor_protegido.nome}</strong> não recebeu pato. Os demais jogadores ativos receberam 1 pato.</p>
            </>
          ) : (
            <>
              <p>Ninguém enviou um palpite.</p>
              <p>Nenhum pato foi aplicado.</p>
            </>
          )}
        </>
      )}
      <p className="np-result__explanation">{rodada.pergunta?.explicacao}</p>
      {rodada.numero < partida.total_rodadas ? (
        jogadorAtivo ? (
          <>
            <p className="np-hint">Qualquer jogador pode iniciar a próxima rodada.</p>
            <button className="np-start-button" type="button" disabled={carregando} onClick={aoIniciarProximaRodada}>
              {carregando ? 'Iniciando próxima rodada...' : 'PRÓXIMA RODADA'}
            </button>
          </>
        ) : (
          <p role="status">Aguardando um jogador ativo iniciar a próxima rodada...</p>
        )
      ) : (
        <p role="status">10 rodadas concluídas. Preparando resultado final...</p>
      )}
    </section>
  )
}

export default NemAPatoRoundResult
