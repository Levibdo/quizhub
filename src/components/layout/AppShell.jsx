import SiteHeader from './SiteHeader'

function AppShell({ children, aoClicarMarca, usuario, navegacao }) {
  return (
    <div className="app-shell">
      <SiteHeader aoClicarMarca={aoClicarMarca} usuario={usuario} {...navegacao} />
      <main className="screen-frame">{children}</main>
    </div>
  )
}

export default AppShell
