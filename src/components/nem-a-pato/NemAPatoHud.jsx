function NemAPatoHud({ carregando, emPartida, podeAbandonar, aoSolicitarSaida }) {
  return (
    <>
      <header className="np-heading">
        <span className="np-eyebrow">QuizHub // Sala multiplayer</span>
        <h1 id="np-title">NEM A PATO!</h1>
        <p>{emPartida ? 'Partida em andamento' : 'Lobby da sala'}</p>
      </header>
      {podeAbandonar && (
        <button className="np-exit-room" type="button" disabled={carregando} onClick={(evento) => aoSolicitarSaida('modo', evento)}>
          SAIR DA SALA
        </button>
      )}
    </>
  )
}

export default NemAPatoHud
