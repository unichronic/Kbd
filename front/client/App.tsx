import "./global.css";

import { Toaster } from "@/components/ui/toaster";
import { createRoot } from "react-dom/client";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import Incidents from "./pages/Incidents";
import Integrations from "./pages/Integrations";
import Settings from "./pages/Settings";
import { Shell } from "@/components/layout/Shell";
import { SystemStatusProvider } from "@/context/SystemStatusContext";
import { ApiProvider } from "@/context/ApiContext";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <ApiProvider>
        <SystemStatusProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <Shell>
              <Routes>
                <Route path="/" element={<Index />} />
                <Route path="/incidents" element={<Incidents />} />
                <Route path="/integrations" element={<Integrations />} />
                <Route path="/settings" element={<Settings />} />
                {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
                <Route path="*" element={<NotFound />} />
              </Routes>
            </Shell>
          </BrowserRouter>
        </SystemStatusProvider>
      </ApiProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

createRoot(document.getElementById("root")!).render(<App />);
