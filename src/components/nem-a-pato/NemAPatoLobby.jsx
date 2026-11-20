import NemAPatoGameResult from './NemAPatoGameResult'
import NemAPatoHud from './NemAPatoHud'
import NemAPatoRound from './NemAPatoRound'
import NemAPatoRoundResult from './NemAPatoRoundResult'
import NemAPatoScoreboard from './NemAPatoScoreboard'

function NemAPatoLobby({
  botaoCancelarDesafioRef,
  botaoCancelarSaidaRef,
  carregando,
  codigoSalaRef,
  confirmacaoDesafio,
  erro,
  estadoTerminalCompleto,
  eu,
  jogadorAtual,
  mensagemSemSessao,
  modalDesafioRef,
  modalSaida,
  modalSaidaRef,
  palpite,
  partida,
  participantes,
  placarFinal,
  podeAbandonar,
  podeDesafiar,
  prazoEsgotado,
  resultadoFinal,
  rodada,
  sala,
  sessao,
  sucesso,
  tempoExibido,
  ultimoPalpite,
  aoAlterarPalpite,
  aoConfirmarDesafio,
  aoConfirmarPalpite,
  aoConterFocoDesafio,
  aoConterFocoSaida,
  aoCopiarCodigo,
  aoFecharDesafio,
  aoFecharSaida,
  aoIniciarPartida,
  aoIniciarProximaRodada,
  aoIniciarRodada,
  aoJogarNovamente,
  aoNavegarInicio,
  aoSairDaSala,
  aoSolicitarDesafio,
  aoSolicitarSaida,
  aoTentarRecuperar,
  aoVoltarInicio,
}) {
  return (
    <section className="np-screen" aria-labelledby="np-title" aria-busy={carregando}>
      <NemAPatoHud
        carregando={carregando}
        emPartida={sala?.status === 'EM_PARTIDA'}
        podeAbandonar={podeAbandonar}
        aoSolicitarSaida={aoSolicitarSaida}
      />
      {mensagemSemSessao && <p className="np-message np-message--error" role="alert">{mensagemSemSessao}</p>}
      {sucesso && <p className="np-message" role="status">{sucesso}</p>}
      {!sala && sessao && !erro && <p className="np-sync" role="status">Recuperando sua participação...</p>}
      {!sala && sessao && erro && (
        <button className="button-secondary np-retry" type="button" disabled={carregando} onClick={aoTentarRecuperar}>
          {carregando ? 'Reconectando...' : 'Tentar novamente'}
        </button>
      )}
      {!sessao && (
        <button className="button-secondary" type="button" onClick={aoNavegarInicio}>
          Voltar para Nem a Pato
        </button>
      )}
      {sala && (
        <>
          {sala.status === 'ENCERRADA' && !estadoTerminalCompleto && (
            <p role="status">Sincronizando resultado final...</p>
          )}
          {estadoTerminalCompleto && partida && (
            <NemAPatoGameResult
              carregando={carregando}
              eu={eu}
              partida={partida}
              placarFinal={placarFinal}
              resultadoFinal={resultadoFinal}
              sala={sala}
              aoJogarNovamente={aoJogarNovamente}
              aoVoltar={aoVoltarInicio}
            />
          )}
          {sala.status === 'EM_PARTIDA' && (
            <section className="np-started" aria-labelledby="np-started-title">
              <p className="np-started__eyebrow">Sala {sala.codigo}</p>
              <h2 id="np-started-title">A PARTIDA COMEÇOU</h2>
              {partida ? (
                <>
                  {partida.numero > 1 && <p className="np-started__eyebrow">REVANCHE</p>}
                  <p>Partida {partida.numero} · {partida.total_rodadas} rodadas · {Math.floor(partida.duracao_rodada_segundos / 60)} minutos por rodada</p>
                  <NemAPatoScoreboard jogadores={partida.jogadores} />
                </>
              ) : <p role="status">Recuperando a partida...</p>}
              {rodada?.status === 'AGUARDANDO_INICIO' && (
                eu?.eh_anfitriao ? (
                  <button className="np-start-button" type="button" disabled={carregando} onClick={aoIniciarRodada}>
                    {carregando ? 'Iniciando rodada...' : 'Iniciar rodada'}
                  </button>
                ) : <p role="status">Aguardando o anfitrião iniciar a rodada...</p>
              )}
              {rodada?.status === 'EM_ANDAMENTO' && (
                <NemAPatoRound
                  botaoCancelarDesafioRef={botaoCancelarDesafioRef}
                  carregando={carregando}
                  confirmacaoDesafio={confirmacaoDesafio}
                  modalDesafioRef={modalDesafioRef}
                  palpite={palpite}
                  partida={partida}
                  podeDesafiar={podeDesafiar}
                  prazoEsgotado={prazoEsgotado}
                  rodada={rodada}
                  tempoExibido={tempoExibido}
                  ultimoPalpite={ultimoPalpite}
                  aoAlterarPalpite={aoAlterarPalpite}
                  aoConfirmarDesafio={aoConfirmarDesafio}
                  aoConfirmarPalpite={aoConfirmarPalpite}
                  aoConterFocoDesafio={aoConterFocoDesafio}
                  aoFecharDesafio={aoFecharDesafio}
                  aoSolicitarDesafio={aoSolicitarDesafio}
                />
              )}
              {rodada?.status === 'RESULTADO' && (
                <NemAPatoRoundResult
                  carregando={carregando}
                  jogadorAtivo={jogadorAtual?.status === 'ATIVO'}
                  partida={partida}
                  rodada={rodada}
                  aoIniciarProximaRodada={aoIniciarProximaRodada}
                />
              )}
            </section>
          )}
          {sala.status === 'AGUARDANDO' && (
            <section className="np-room-code" aria-label="Código da sala">
              <label htmlFor="np-room-code-value">Código da sala</label>
              <input ref={codigoSalaRef} id="np-room-code-value" type="text" readOnly value={sala.codigo} aria-describedby="np-room-code-help" onFocus={(evento) => evento.currentTarget.select()} />
              <p id="np-room-code-help">Compartilhe este código com os outros jogadores. Você também pode selecionar o campo e copiar manualmente.</p>
              <button className="button-secondary" type="button" onClick={aoCopiarCodigo}>Copiar código</button>
            </section>
          )}
          {sala.status === 'AGUARDANDO' && <p className="np-room-count">{sala.participantes_ativos} / {sala.limite_jogadores} jogadores</p>}
          {sala.status === 'AGUARDANDO' && (
            <ul className="np-player-list" aria-label="Participantes da sala">
              {participantes.map((participante) => (
                <li key={participante.id} className="np-player">
                  <span aria-hidden="true">{participante.eh_anfitriao ? '♛' : '♙'}</span>
                  <strong>{participante.nome}</strong>
                  {participante.eh_anfitriao && <span className="np-player__badge">Anfitrião</span>}
                  {eu?.id === participante.id && <span className="np-player__you">Você</span>}
                </li>
              ))}
            </ul>
          )}
          {sala.status === 'AGUARDANDO' && (
            <>
              <p className="np-lobby-status">{eu?.eh_anfitriao ? 'Sala pronta para receber jogadores.' : 'Aguardando o anfitrião iniciar a partida.'}</p>
              {eu?.eh_anfitriao && <p className="np-host-note">Você é o anfitrião.</p>}
              {sala.participantes_ativos < 3 && <p className="np-hint">Aguardando pelo menos 3 jogadores.</p>}
              {eu?.eh_anfitriao && (
                <button className="np-start-button" type="button" disabled={carregando || sala.participantes_ativos < 3 || sala.participantes_ativos > sala.limite_jogadores} onClick={aoIniciarPartida}>
                  {carregando ? 'Iniciando...' : 'Iniciar partida'}
                </button>
              )}
            </>
          )}
          {modalSaida && (
            <div className="np-dialog-backdrop" role="presentation">
              <section ref={modalSaidaRef} onKeyDown={aoConterFocoSaida} tabIndex={-1} className="np-dialog" role="dialog" aria-modal="true" aria-labelledby="np-exit-title" aria-describedby="np-exit-description">
                <p className="np-eyebrow">QuizHub // Sala multiplayer</p>
                <h4 id="np-exit-title">{modalSaida.tipo === 'bloqueio' ? 'RODADA EM ANDAMENTO' : 'SAIR DA SALA?'}</h4>
                <p id="np-exit-description">
                  {modalSaida.tipo === 'bloqueio'
                    ? 'Você está em uma rodada em andamento. Para evitar abandonar a partida no meio da rodada, aguarde o resultado para sair da sala.'
                    : 'Você deixará esta partida e não poderá retornar com esta participação.'}
                </p>
                {erro && <p className="np-message np-message--error" role="alert">{erro}</p>}
                <div className="np-dialog__actions">
                  {modalSaida.tipo === 'confirmacao' && (
                    <button className="np-leave" type="button" disabled={carregando} onClick={aoSairDaSala}>
                      {carregando ? 'Saindo da sala...' : modalSaida.destino === 'home' ? 'SAIR E VOLTAR AO INÍCIO' : 'SAIR DA SALA'}
                    </button>
                  )}
                  <button ref={botaoCancelarSaidaRef} className="button-secondary" type="button" disabled={carregando} onClick={aoFecharSaida}>
                    {modalSaida.tipo === 'bloqueio' ? 'CONTINUAR NA PARTIDA' : 'CANCELAR'}
                  </button>
                </div>
              </section>
            </div>
          )}
        </>
      )}
    </section>
  )
}

export default NemAPatoLobby
