import { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarSeparator,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import { Box, LayoutDashboard, AlertTriangle, Cloud, Plug, Settings, CheckCircle2, XCircle } from "lucide-react";
import { useSystemStatus } from "@/context/SystemStatusContext";

function Logo() {
  return (
    <div className="flex items-center gap-2 px-2 py-1">
      <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary">
        <Box className="h-5 w-5" />
      </div>
      <span className="text-lg font-semibold tracking-tight">KubeeDoo</span>
    </div>
  );
}

function SystemStatusPill() {
  const { level, message } = useSystemStatus();
  const color = level === "critical" ? "bg-destructive text-destructive-foreground" : level === "warning" ? "bg-warning text-black" : "bg-success text-white";
  const Icon = level === "critical" ? XCircle : CheckCircle2;
  return (
    <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm ${color}`}>
      <Icon className="h-4 w-4" />
      {message}
    </span>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <Logo />
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive tooltip="Dashboard">
                    <NavLink to="/">
                      <LayoutDashboard />
                      <span>Dashboard</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild tooltip="Incidents">
                    <NavLink to="/incidents">
                      <AlertTriangle />
                      <span>Incidents</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild tooltip="Infrastructure">
                    <NavLink to="/infrastructure">
                      <Cloud />
                      <span>Infrastructure</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild tooltip="Integrations">
                    <NavLink to="/integrations">
                      <Plug />
                      <span>Integrations</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild tooltip="Settings">
                    <NavLink to="/settings">
                      <Settings />
                      <span>Settings</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarSeparator />
        <SidebarFooter>
          <div className="px-2">
            <Badge variant="secondary" className="w-full justify-center">v1.0</Badge>
          </div>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <header className="sticky top-0 z-20 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="flex h-16 items-center justify-between px-4">
            <div className="flex items-center gap-3">
              <SidebarTrigger />
              <Separator orientation="vertical" className="mx-2 h-6" />
              <Logo />
            </div>
            <div className="flex items-center gap-4">
              <SystemStatusPill />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="gap-3">
                    <Avatar className="h-8 w-8">
                      <AvatarFallback>UD</AvatarFallback>
                    </Avatar>
                    <span className="hidden sm:inline">unichronic</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>My Account</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem>Profile</DropdownMenuItem>
                  <DropdownMenuItem>Billing</DropdownMenuItem>
                  <DropdownMenuItem>Settings</DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem>Sign out</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>
        <main className="p-4 md:p-6 lg:p-8">
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
