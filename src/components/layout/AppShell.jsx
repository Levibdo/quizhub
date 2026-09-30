import SiteHeader from './SiteHeader'

function AppShell({ children }) {
  return (
    <div className="app-shell">
      <SiteHeader />
      <main className="screen-frame">{children}</main>
    </div>
  )
}

export default AppShell
