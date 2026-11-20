function NemAPatoScoreboard({ jogadores }) {
  return (
    <section className="np-score" aria-label="Placar de patos">
      <h3>PATOS</h3>
      <ul>
        {jogadores.map((jogador) => (
          <li key={jogador.id}>
            <span>{jogador.nome}</span>
            <strong>{jogador.patos ?? 0} 🦆{jogador.eh_eu && <small>Você</small>}</strong>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default NemAPatoScoreboard
