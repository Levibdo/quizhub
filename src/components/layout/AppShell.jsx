import SiteHeader from './SiteHeader'

function AppShell({ children, aoClicarMarca, usuario, navegacao, imersivo = false }) {
  return (
    <div className={`app-shell${imersivo ? ' app-shell--immersive' : ''}`}>
      <SiteHeader aoClicarMarca={aoClicarMarca} usuario={usuario} {...navegacao} />
      <main className={imersivo ? 'immersive-frame' : 'screen-frame'}>{children}</main>
    </div>
  )
}

export default AppShell
