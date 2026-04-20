import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom"
import Dashboard from "@/pages/Dashboard"
import Config from "@/pages/Config"
import Neighbors from "@/pages/Neighbors"
import Logs from "@/pages/Logs"

const navItems = [
  { to: "/", label: "Dashboard" },
  { to: "/config", label: "Config" },
  { to: "/neighbors", label: "Neighbors" },
  { to: "/logs", label: "Logs" },
]

function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen">
        {/* Sidebar */}
        <aside className="w-56 border-r bg-sidebar p-4 flex flex-col gap-1">
          <h2 className="text-lg font-bold mb-4 px-2">MeshCore</h2>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/50"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/config" element={<Config />} />
            <Route path="/neighbors" element={<Neighbors />} />
            <Route path="/logs" element={<Logs />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
