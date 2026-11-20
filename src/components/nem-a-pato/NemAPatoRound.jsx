import { formatarPalpite, formatarTempo } from './formatters'

function NemAPatoRound({
  botaoCancelarDesafioRef,
  carregando,
  confirmacaoDesafio,
  modalDesafioRef,
  palpite,
  partida,
  podeDesafiar,
  prazoEsgotado,
  rodada,
  tempoExibido,
  ultimoPalpite,
  aoAlterarPalpite,
  aoConfirmarDesafio,
  aoConfirmarPalpite,
  aoConterFocoDesafio,
  aoFecharDesafio,
  aoSolicitarDesafio,
}) {
  return (
    <section className="np-round" aria-labelledby="np-round-title">
      <header className="np-round__header">
        <p className="np-round__counter">Rodada {rodada.numero} de {partida.total_rodadas}</p>
        <p className={tempoExibido <= 10 ? 'np-timer np-timer--urgent' : 'np-timer'} aria-label={`${tempoExibido} segundos restantes`}>
          <span>Tempo</span><strong>{formatarTempo(tempoExibido)}</strong>
        </p>
      </header>
      <h3 id="np-round-title" className="np-visually-hidden">Pergunta</h3>
      <p className="np-round__question">{rodada.pergunta?.enunciado}</p>
      {rodada.pergunta?.unidade && <p className="np-round__unit">Responda em <strong>{rodada.pergunta.unidade}</strong></p>}
      <div className="np-round__status">
        <p>Maior palpite <strong>{formatarPalpite(rodada.maior_palpite, rodada.pergunta?.unidade)}</strong></p>
        <p className={rodada.jogador_da_vez?.eh_eu ? 'np-turn np-turn--you' : 'np-turn'}>
          <span className="np-visually-hidden">Jogador da vez: </span>
          {rodada.jogador_da_vez?.eh_eu ? 'Sua vez' : 'Vez de'}
          <strong>{rodada.jogador_da_vez?.eh_eu ? 'Faça seu palpite' : rodada.jogador_da_vez?.nome}</strong>
        </p>
      </div>
      {prazoEsgotado && <p className="np-sync" role="status">TEMPO ESGOTADO — confirmando resultado...</p>}
      {rodada.palpites.length > 0 && (
        <ol className="np-guess-history" aria-label="Histórico de palpites">
          {rodada.palpites.map((item, indice) => (
            <li className={indice === rodada.palpites.length - 1 ? 'np-guess-history__latest' : ''} key={item.ordem}>
              <span>{item.jogador.nome}</span>
              <strong>{formatarPalpite(item.valor, rodada.pergunta?.unidade)}</strong>
            </li>
          ))}
        </ol>
      )}
      {rodada.jogador_da_vez?.eh_eu && !prazoEsgotado ? (
        <form className="np-guess-form" onSubmit={aoConfirmarPalpite}>
          <label htmlFor="np-guess">Seu palpite</label>
          {rodada.maior_palpite !== null && rodada.maior_palpite !== undefined && (
            <p id="np-guess-hint">Seu palpite deve ser maior que {formatarPalpite(rodada.maior_palpite, rodada.pergunta?.unidade)}.</p>
          )}
          <input
            id="np-guess"
            type="number"
            inputMode="numeric"
            pattern="[0-9]*"
            min="0"
            step="1"
            aria-describedby={rodada.maior_palpite !== null && rodada.maior_palpite !== undefined ? 'np-guess-hint' : undefined}
            value={palpite}
            onChange={(event) => aoAlterarPalpite(event.target.value)}
            disabled={carregando || prazoEsgotado}
            required
          />
          <button type="submit" disabled={carregando || !palpite}>
            {carregando ? 'Enviando...' : 'Confirmar palpite'}
          </button>
        </form>
      ) : !prazoEsgotado ? (
        <p role="status">Aguardando o palpite de {rodada.jogador_da_vez?.nome}...</p>
      ) : null}
      {podeDesafiar && (
        <button className="np-challenge" type="button" disabled={carregando} onClick={aoSolicitarDesafio}>
          {carregando ? 'Desafiando...' : 'NEM A PATO!'}
        </button>
      )}
      {confirmacaoDesafio && ultimoPalpite && (
        <div className="np-dialog-backdrop" role="presentation">
          <section ref={modalDesafioRef} onKeyDown={aoConterFocoDesafio} tabIndex={-1} className="np-dialog" role="dialog" aria-modal="true" aria-labelledby="np-challenge-title" aria-describedby="np-challenge-description">
            <p className="np-eyebrow">Confirme o desafio</p>
            <h4 id="np-challenge-title">NEM A PATO!</h4>
            <p id="np-challenge-description">Você quer desafiar o palpite de <strong>{ultimoPalpite.jogador.nome}: {formatarPalpite(ultimoPalpite.valor, rodada.pergunta?.unidade)}</strong>?</p>
            <div className="np-dialog__actions">
              <button type="button" className="np-challenge" disabled={carregando} onClick={aoConfirmarDesafio}>
                {carregando ? 'Confirmando desafio...' : 'CONFIRMAR DESAFIO'}
              </button>
              <button ref={botaoCancelarDesafioRef} type="button" className="button-secondary" disabled={carregando} onClick={aoFecharDesafio}>
                CANCELAR
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  )
}

export default NemAPatoRound
