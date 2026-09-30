function QuestionCard({ children }) {
  return (
    <section className="question-card" aria-labelledby="question-title">
      <span className="question-card__eyebrow">Enunciado</span>
      <h1 id="question-title">{children}</h1>
    </section>
  )
}

export default QuestionCard
