import SiteHeader from './SiteHeader'

function AppShell({ children, aoClicarMarca }) {
  return (
    <div className="app-shell">
      <SiteHeader aoClicarMarca={aoClicarMarca} />
      <main className="screen-frame">{children}</main>
    </div>
  )
}

export default AppShell
