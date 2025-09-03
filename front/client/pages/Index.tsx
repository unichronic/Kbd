import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertTriangle,
  Bot,
  Cpu,
  GitCommitVertical,
  HardDrive,
  RefreshCcw,
  Gauge,
  Clock3,
  Database,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useSystemStatus } from "@/context/SystemStatusContext";
import { useApi } from "@/context/ApiContext";
import { Incident } from "@/lib/api";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import ChatWidget from "@/components/ChatWidget";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Severity = "critical" | "warning" | "info";

type IncidentEventType =
  | "incidents.new"
  | "incidents.resolved"
  | "learner.vectorized";

type IncidentEvent = {
  type: IncidentEventType;
  incidentId: string;
  ts: number;
};

function computeMttr(events: IncidentEvent[]) {
  const byId: Record<string, IncidentEvent[]> = {};
  for (const e of events) {
    (byId[e.incidentId] ||= []).push(e);
  }
  const durations: number[] = [];
  for (const id of Object.keys(byId)) {
    const evs = byId[id].slice().sort((a, b) => a.ts - b.ts);
    let open: number | null = null;
    for (const e of evs) {
      if (e.type === "incidents.new") open = e.ts;
      if (e.type === "incidents.resolved" && open != null && e.ts >= open) {
        durations.push(e.ts - open);
        open = null;
      }
    }
  }
  const avgMs = durations.length
    ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
    : 0;
  return { avgMs, durations };
}

function formatDuration(ms: number) {
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${seconds}s`;
}

export default function Index() {
  const { setStatus } = useSystemStatus();
  const { 
    apiClient, 
    isApiConnected, 
    wsConnectionState, 
    healthStatus, 
    isLoading, 
    error,
    refreshHealth 
  } = useApi();

  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [incidentsLoading, setIncidentsLoading] = useState(false);
  const [aiMode, setAiMode] = useState<"manual" | "low" | "medium" | "high">("manual");

  // Mock events for MTTR calculation (replace with real data later)
  const events = useMemo<IncidentEvent[]>(() => {
    const now = Date.now();
    return [
      {
        type: "incidents.new",
        incidentId: "INC-1024",
        ts: now - 45 * 60 * 1000,
      },
      {
        type: "incidents.resolved",
        incidentId: "INC-1024",
        ts: now - 15 * 60 * 1000,
      },
      {
        type: "incidents.new",
        incidentId: "INC-1023",
        ts: now - 3 * 60 * 60 * 1000,
      },
      {
        type: "incidents.resolved",
        incidentId: "INC-1023",
        ts: now - 2 * 60 * 60 * 1000 - 20 * 60 * 1000,
      },
    ];
  }, []);

  const { avgMs: mttrMs, durations: mttrDurations } = useMemo(
    () => computeMttr(events),
    [events],
  );
  const mttrDisplay = formatDuration(mttrMs);
  const mttrSeries = useMemo(() => {
    const data = mttrDurations
      .slice(-12)
      .map((d, i) => ({ x: i, mttrMin: Math.max(0, Math.round(d / 60000)) }));
    return data.length ? data : [{ x: 0, mttrMin: 0 }];
  }, [mttrDurations]);

  const learnedCount = useMemo(() => {
    const ids = new Set(
      events
        .filter((e) => e.type === "learner.vectorized")
        .map((e) => e.incidentId),
    );
    return ids.size;
  }, [events]);

  // Load incidents from API
  const loadIncidents = async () => {
    try {
      setIncidentsLoading(true);
      const incidentsData = await apiClient.getIncidents();
      setIncidents(incidentsData);
    } catch (err) {
      console.error('Failed to load incidents:', err);
      // Fallback to mock data if API fails
      setIncidents([
        {
          id: "INC-1024",
          title: "Spike in 5xx responses on api-gateway",
          severity: "critical",
          status: "active",
          hypothesis: "Possible upstream timeout in user-service",
          occurredAt: "2m ago",
          service: "api-gateway"
        },
        {
          id: "INC-1023",
          title: "Elevated pod restarts in kube-system",
          severity: "warning",
          status: "acknowledged",
          hypothesis: "Node drain during autoscaling event",
          occurredAt: "14m ago",
          service: "kubelet"
        },
      ]);
    } finally {
      setIncidentsLoading(false);
    }
  };

  // Load initial data
  useEffect(() => {
    loadIncidents();
  }, []);

  // Mock metrics (replace with real data later)
  const cpu = 62;
  const mem = 71;
  const restarts = 5;
  const activeAlerts = incidents.filter(
    (i) => i.severity !== "info",
  ).length;

  const systemLevel = useMemo(() => {
    const hasCritical = incidents.some((i) => i.severity === "critical");
    const hasWarning = incidents.some((i) => i.severity === "warning");
    if (hasCritical)
      return {
        level: "critical" as const,
        message: `${activeAlerts} Active Incidents`,
      };
    if (hasWarning)
      return {
        level: "warning" as const,
        message: `${activeAlerts} Active Alerts`,
      };
    return {
      level: "operational" as const,
      message: "All Systems Operational",
    };
  }, [activeAlerts, incidents]);

  useEffect(() => {
    setStatus(systemLevel);
  }, [setStatus, systemLevel]);

  return (
    <div className="mx-auto w-full max-w-[1600px]">
      {/* Connection Status Alert */}
      {error && (
        <Alert className="mb-6" variant="destructive">
          <WifiOff className="h-4 w-4" />
          <AlertDescription>
            {error} - Some features may not work properly.
          </AlertDescription>
        </Alert>
      )}

      {!isApiConnected && (
        <Alert className="mb-6" variant="warning">
          <Wifi className="h-4 w-4" />
          <AlertDescription>
            Backend connection lost. Attempting to reconnect...
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-12 gap-6 auto-rows-[minmax(120px,auto)]">
        {/* Correlated Incidents Feed */}
        <Card className="col-span-12 xl:col-span-8 xl:row-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-xl">
              <AlertTriangle className="h-5 w-5 text-warning" /> Correlated
              Incidents
            </CardTitle>
            <Button 
              variant="secondary" 
              size="sm" 
              className="gap-2"
              onClick={loadIncidents}
              disabled={incidentsLoading}
            >
              <RefreshCcw className={`h-4 w-4 ${incidentsLoading ? 'animate-spin' : ''}`} /> 
              Refresh
            </Button>
          </CardHeader>
          <CardContent className="pt-2">
            <ScrollArea className="h-[420px] pr-4">
              <ul className="space-y-3">
                {incidents.map((inc) => (
                  <li
                    key={inc.id}
                    className="rounded-lg border p-4 hover:bg-accent"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-medium">
                            {inc.title}
                          </span>
                          {inc.severity === "critical" && (
                            <Badge className="bg-destructive text-destructive-foreground">
                              Critical
                            </Badge>
                          )}
                          {inc.severity === "warning" && (
                            <Badge className="bg-warning text-black">
                              Warning
                            </Badge>
                          )}
                          {inc.severity === "info" && (
                            <Badge variant="secondary">Info</Badge>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground truncate">
                          AI hypothesis: {inc.hypothesis}
                        </p>
                      </div>
                      <span className="shrink-0 text-sm text-muted-foreground">
                        {inc.occurredAt}
                      </span>
                    </div>
                  </li>
                ))}
                {incidents.length === 0 && !incidentsLoading && (
                  <li className="rounded-lg border p-6 text-center text-muted-foreground">
                    No incidents found
                  </li>
                )}
                {incidentsLoading && (
                  <li className="rounded-lg border p-6 text-center text-muted-foreground">
                    Loading incidents...
                  </li>
                )}
              </ul>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* AFK Mode Control */}
        <Card className="col-span-12 xl:col-span-4">
          <CardHeader>
            <CardTitle className="text-xl flex items-center gap-2">
              <Bot className="h-5 w-5 text-primary" /> AFK Mode
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border p-1 bg-muted/50">
              <div className="grid grid-cols-4 gap-1">
                {(
                  [
                    { k: "manual", label: "Manual" },
                    { k: "low", label: "Low" },
                    { k: "medium", label: "Medium" },
                    { k: "high", label: "High" },
                  ] as const
                ).map(({ k, label }) => (
                  <button
                    key={k}
                    onClick={() => setAiMode(k)}
                    className={`h-10 rounded-md text-sm font-medium transition-colors ${
                      aiMode === k
                        ? "bg-primary text-primary-foreground"
                        : "hover:bg-accent"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              {aiMode === "manual" && "AFK disabled. AI only suggests actions."}
              {aiMode === "low" &&
                "AFK on (Low): handles minor, predefined issues."}
              {aiMode === "medium" &&
                "AFK on (Medium): manages moderate incidents."}
              {aiMode === "high" &&
                "AFK on (High): full autonomy on critical issues."}
            </p>
          </CardContent>
        </Card>

        {/* KPI row */}
        <div className="col-span-12 grid grid-cols-12 gap-6">
          <Card className="col-span-12 sm:col-span-6 lg:col-span-3">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Cpu className="h-4 w-4" /> Cluster CPU Usage
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-2xl font-semibold">{cpu}%</span>
                <Badge variant="secondary">5m</Badge>
              </div>
              <div className="h-24">
                <ChartContainer
                  config={{
                    cpu: { label: "CPU", color: "hsl(var(--primary))" },
                  }}
                >
                  <AreaChart
                    data={Array.from({ length: 30 }, (_, i) => ({
                      x: i,
                      cpu: Math.max(
                        0,
                        Math.min(100, cpu + Math.sin(i / 3) * 8 + (i % 5) - 2),
                      ),
                    }))}
                  >
                    <defs>
                      <linearGradient id="cpuFill" x1="0" x2="0" y1="0" y2="1">
                        <stop
                          offset="5%"
                          stopColor="hsl(var(--primary))"
                          stopOpacity={0.35}
                        />
                        <stop
                          offset="95%"
                          stopColor="hsl(var(--primary))"
                          stopOpacity={0.02}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" />
                    <XAxis dataKey="x" hide />
                    <YAxis domain={[0, 100]} hide />
                    <Tooltip content={<ChartTooltipContent />} />
                    <Area
                      type="monotone"
                      dataKey="cpu"
                      stroke="hsl(var(--primary))"
                      fill="url(#cpuFill)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ChartContainer>
              </div>
            </CardContent>
          </Card>

          <Card className="col-span-12 sm:col-span-6 lg:col-span-3">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <HardDrive className="h-4 w-4" /> Cluster Memory Usage
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-2xl font-semibold">{mem}%</span>
                <Badge variant="secondary">5m</Badge>
              </div>
              <div className="h-24">
                <ChartContainer
                  config={{
                    mem: {
                      label: "Mem",
                      color: "hsl(var(--accent-foreground))",
                    },
                  }}
                >
                  <AreaChart
                    data={Array.from({ length: 30 }, (_, i) => ({
                      x: i,
                      mem: Math.max(
                        0,
                        Math.min(
                          100,
                          mem + Math.cos(i / 4) * 6 + ((i * 3) % 7) - 3,
                        ),
                      ),
                    }))}
                  >
                    <defs>
                      <linearGradient id="memFill" x1="0" x2="0" y1="0" y2="1">
                        <stop
                          offset="5%"
                          stopColor="hsl(var(--accent-foreground))"
                          stopOpacity={0.35}
                        />
                        <stop
                          offset="95%"
                          stopColor="hsl(var(--accent-foreground))"
                          stopOpacity={0.02}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" />
                    <XAxis dataKey="x" hide />
                    <YAxis domain={[0, 100]} hide />
                    <Tooltip content={<ChartTooltipContent />} />
                    <Area
                      type="monotone"
                      dataKey="mem"
                      stroke="hsl(var(--accent-foreground))"
                      fill="url(#memFill)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ChartContainer>
              </div>
            </CardContent>
          </Card>

          <Card className="col-span-12 sm:col-span-6 lg:col-span-3">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <RefreshCcw className="h-4 w-4" /> Pod Restart Rate
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-2xl font-semibold">{restarts}</span>
                <Badge variant="secondary">/ hr</Badge>
              </div>
            </CardContent>
          </Card>

          <Card className="col-span-12 sm:col-span-6 lg:col-span-3">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Clock3 className="h-4 w-4" /> MTTR
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-2xl font-semibold">{mttrDisplay}</span>
                <Badge variant="secondary">last 10</Badge>
              </div>
              <div className="h-24">
                <ChartContainer
                  config={{
                    mttrMin: {
                      label: "MTTR (min)",
                      color: "hsl(var(--primary))",
                    },
                  }}
                >
                  <AreaChart data={mttrSeries}>
                    <defs>
                      <linearGradient id="mttrFill" x1="0" x2="0" y1="0" y2="1">
                        <stop
                          offset="5%"
                          stopColor="hsl(var(--primary))"
                          stopOpacity={0.35}
                        />
                        <stop
                          offset="95%"
                          stopColor="hsl(var(--primary))"
                          stopOpacity={0.02}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" />
                    <XAxis dataKey="x" hide />
                    <YAxis hide />
                    <Tooltip content={<ChartTooltipContent />} />
                    <Area
                      type="monotone"
                      dataKey="mttrMin"
                      stroke="hsl(var(--primary))"
                      fill="url(#mttrFill)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ChartContainer>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Activity Feed */}
        <Card className="col-span-12 lg:col-span-10">
          <CardHeader>
            <CardTitle className="text-xl flex items-center gap-2">
              <GitCommitVertical className="h-5 w-5" /> Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="code">
              <TabsList>
                <TabsTrigger value="code">Recent Code Changes</TabsTrigger>
                <TabsTrigger value="ai">Recent AI Actions</TabsTrigger>
              </TabsList>
              <TabsContent value="code">
                <ul className="mt-2 space-y-3">
                  {[
                    {
                      msg: "feat(payments): add retries for webhook handler",
                      t: "28m ago",
                    },
                    { msg: "chore: bump kubectl to 1.31.1", t: "1h ago" },
                    { msg: "fix(auth): reduce token TTL to 15m", t: "2h ago" },
                  ].map((c, i) => (
                    <li key={i} className="rounded-lg border p-3">
                      <div className="flex items-center justify-between">
                        <span className="truncate">{c.msg}</span>
                        <span className="text-sm text-muted-foreground">
                          {c.t}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </TabsContent>
              <TabsContent value="ai">
                <ul className="mt-2 space-y-3">
                  {[
                    "Restarted pod payments-7bcd9d5fbc-2zktm after crashloop",
                    "Scaled api-gateway from 6 -> 8 replicas due to traffic spike",
                    "Opened incident INC-1024 with correlated logs",
                  ].map((a, i) => (
                    <li key={i} className="rounded-lg border p-3">
                      {a}
                    </li>
                  ))}
                </ul>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        {/* Learned Incidents */}
        <Card className="col-span-12 lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Database className="h-4 w-4" /> Total Learned Incidents
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-semibold">{learnedCount}</span>
              <Badge variant="secondary">ChromaDB</Badge>
            </div>
          </CardContent>
        </Card>
      </div>
      <ChatWidget />
    </div>
  );
}