import { lazy, Suspense } from "react"
import { BrowserRouter, Routes, Route, NavLink, useLocation } from "react-router-dom"
import {
  SidebarProvider,
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import { LayoutDashboardIcon, SettingsIcon, UsersIcon, ScrollTextIcon } from "lucide-react"

const Dashboard = lazy(() => import("@/pages/Dashboard"))
const Config = lazy(() => import("@/pages/Config"))
const Neighbors = lazy(() => import("@/pages/Neighbors"))
const Logs = lazy(() => import("@/pages/Logs"))

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboardIcon },
  { to: "/config", label: "Config", icon: SettingsIcon },
  { to: "/neighbors", label: "Neighbors", icon: UsersIcon },
  { to: "/logs", label: "Logs", icon: ScrollTextIcon },
]

function AppShell() {
  const location = useLocation()

  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader>
          <span className="px-2 text-lg font-bold">MeshCore</span>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Navigation</SidebarGroupLabel>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    render={<NavLink to={item.to} end={item.to === "/"} />}
                    isActive={
                      item.to === "/"
                        ? location.pathname === "/"
                        : location.pathname.startsWith(item.to)
                    }
                  >
                    <item.icon />
                    {item.label}
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>
      </Sidebar>
      <SidebarInset>
        <main className="flex-1 overflow-y-auto p-6">
          <Suspense
            fallback={
              <div className="flex flex-col gap-4">
                <Skeleton className="h-8 w-48" />
                <Skeleton className="h-64 w-full" />
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/config" element={<Config />} />
              <Route path="/neighbors" element={<Neighbors />} />
              <Route path="/logs" element={<Logs />} />
            </Routes>
          </Suspense>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  )
}

export default App
