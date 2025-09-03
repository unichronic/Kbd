import { createContext, useContext, useState, ReactNode } from "react";

export type StatusLevel = "operational" | "warning" | "critical";

export interface SystemStatus {
  level: StatusLevel;
  message: string;
}

interface Ctx extends SystemStatus {
  setStatus: (s: SystemStatus) => void;
}

const SystemStatusContext = createContext<Ctx | null>(null);

export function SystemStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SystemStatus>({
    level: "operational",
    message: "All Systems Operational",
  });

  return (
    <SystemStatusContext.Provider value={{ ...status, setStatus }}>
      {children}
    </SystemStatusContext.Provider>
  );
}

export function useSystemStatus() {
  const ctx = useContext(SystemStatusContext);
  if (!ctx) throw new Error("useSystemStatus must be used within SystemStatusProvider");
  return ctx;
}
