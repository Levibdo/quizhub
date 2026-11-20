function NemAPatoGameResult({
  carregando,
  eu,
  partida,
  placarFinal,
  resultadoFinal,
  sala,
  aoJogarNovamente,
  aoVoltar,
}) {
  return (
    <section className="np-final" aria-labelledby="np-final-title">
      <p className="np-final__eyebrow">Nem a Pato!</p>
      <h2 id="np-final-title">
        {partida.status === 'CANCELADA' ? 'PARTIDA CANCELADA' : 'FIM DE JOGO'}
      </h2>
      {partida.status === 'CANCELADA' ? (
        <p>Não há jogadores ativos suficientes para continuar.</p>
      ) : resultadoFinal?.empate_geral ? (
        <section className="np-final__highlight">
          <h3>EMPATE GERAL</h3>
          <p>Todo mundo venceu. Todo mundo também virou Pato da Partida.</p>
        </section>
      ) : (
        <div className="np-final__extremes">
          <section>
            <h3>{resultadoFinal?.vencedores.length > 1 ? 'VENCEDORES' : 'VENCEDOR'}</h3>
            <strong>{resultadoFinal?.vencedores.map((jogador) => jogador.nome).join(' • ')}</strong>
            <span>{resultadoFinal?.vencedores[0]?.patos} patos</span>
          </section>
          <section>
            <h3>{resultadoFinal?.patos_da_partida.length > 1 ? 'PATOS DA PARTIDA' : 'PATO DA PARTIDA'}</h3>
            <strong>{resultadoFinal?.patos_da_partida.map((jogador) => jogador.nome).join(' • ')}</strong>
            <span>{resultadoFinal?.patos_da_partida[0]?.patos} patos</span>
          </section>
        </div>
      )}
      <section className="np-final__score" aria-label="Placar final">
        <h3>PLACAR FINAL</h3>
        <ol>
          {placarFinal.map((jogador) => (
            <li key={jogador.id}>
              <span>{jogador.nome}</span><strong>{jogador.patos} 🦆</strong>
            </li>
          ))}
        </ol>
      </section>
      {resultadoFinal?.abandonados.length > 0 && (
        <section className="np-final__abandoned">
          <h3>ABANDONARAM</h3>
          {resultadoFinal.abandonados.map((jogador) => (
            <p key={jogador.id}>{jogador.nome} — {jogador.patos} patos</p>
          ))}
        </section>
      )}
      {partida.status === 'FINALIZADA' && eu?.eh_anfitriao && sala.participantes_ativos >= 3 && (
        <button className="np-start-button" type="button" disabled={carregando} onClick={aoJogarNovamente}>
          {carregando ? 'Preparando revanche...' : 'JOGAR NOVAMENTE'}
        </button>
      )}
      {partida.status === 'FINALIZADA' && !eu?.eh_anfitriao && (
        <p role="status">Esperando o anfitrião decidir se haverá revanche...</p>
      )}
      <button className="np-start-button" type="button" onClick={aoVoltar}>
        VOLTAR AO INÍCIO
      </button>
    </section>
  )
}

export default NemAPatoGameResult
