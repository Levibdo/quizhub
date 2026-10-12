export function CosmicEye() {
  return (
    <>
      <path className="cosmic-sigil__eye" d="M52 121c17-27 40-41 68-41s51 14 68 41c-17 27-40 41-68 41s-51-14-68-41Z" />
      <circle className="cosmic-sigil__iris" cx="120" cy="121" r="25" />
      <path className="cosmic-sigil__pupil" d="M120 94c10 11 15 20 15 27s-5 16-15 27c-10-11-15-20-15-27s5-16 15-27Z" />
      <circle className="cosmic-sigil__glint" cx="128" cy="110" r="4" />
    </>
  )
}

function CosmicSigil({ compacto = false }) {
  return (
    <svg
      className={`cosmic-sigil${compacto ? ' cosmic-sigil--compact' : ''}`}
      viewBox="0 0 240 240"
      aria-hidden="true"
      focusable="false"
    >
      <circle className="cosmic-sigil__orbit cosmic-sigil__orbit--outer" cx="120" cy="120" r="101" />
      <circle className="cosmic-sigil__orbit cosmic-sigil__orbit--inner" cx="120" cy="120" r="78" />
      <path className="cosmic-sigil__runes" d="M120 10v20M120 210v20M10 120h20M210 120h20M42 42l14 14M184 184l14 14M198 42l-14 14M56 184l-14 14" />
      <path className="cosmic-sigil__constellation" d="m56 84 25-31 39 18 38-24 27 40-13 49 20 31-43 20-29 35-31-39-47-16 23-39-9-44Z" />
      <circle className="cosmic-sigil__star" cx="81" cy="53" r="3" />
      <circle className="cosmic-sigil__star" cx="158" cy="47" r="2.5" />
      <circle className="cosmic-sigil__star" cx="192" cy="167" r="3" />
      <circle className="cosmic-sigil__star" cx="42" cy="167" r="2.5" />
      <CosmicEye />
    </svg>
  )
}

export default CosmicSigil
