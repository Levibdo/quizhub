import SiteHeader from './SiteHeader'

function AppShell({ children, aoClicarMarca, usuario }) {
  return (
    <div className="app-shell">
      <SiteHeader aoClicarMarca={aoClicarMarca} usuario={usuario} />
      <main className="screen-frame">{children}</main>
    </div>
  )
}

export default AppShell
