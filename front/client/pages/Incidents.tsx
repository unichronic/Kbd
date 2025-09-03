import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  GitCommit,
  PlayCircle,
  Search,
  XCircle,
} from "lucide-react";
import { useApi } from "@/context/ApiContext";

type Severity = "critical" | "warning" | "info";
type Status = "active" | "acknowledged" | "resolved";

type Incident = {
  id: string;
  title: string;
  service: string;
  severity: Severity;
  status: Status;
  updated: string;
  hypothesis: string;
};

const INCIDENTS: Incident[] = [
  {
    id: "INC-1024",
    title: "Spike in 5xx responses on api-gateway",
    service: "api-gateway",
    severity: "critical",
    status: "active",
    updated: "2m ago",
    hypothesis: "Possible upstream timeout in user-service",
  },
  {
    id: "INC-1023",
    title: "Elevated pod restarts in kube-system",
    service: "kubelet",
    severity: "warning",
    status: "acknowledged",
    updated: "14m ago",
    hypothesis: "Node drain during autoscaling event",
  },
  {
    id: "INC-1022",
    title: "Latency regression on payments-service",
    service: "payments",
    severity: "info",
    status: "resolved",
    updated: "1h ago",
    hypothesis: "Recent deploy increased cold-starts",
  },
  {
    id: "INC-1021",
    title: "Error rates increased on auth-service",
    service: "auth",
    severity: "warning",
    status: "active",
    updated: "2h ago",
    hypothesis: "Redis cache saturation causing timeouts",
  },
];

function SeverityBadge({ s }: { s: Severity }) {
  if (s === "critical")
    return (
      <Badge className="bg-destructive text-destructive-foreground">
        Critical
      </Badge>
    );
  if (s === "warning")
    return <Badge className="bg-warning text-black">Warning</Badge>;
  return <Badge variant="secondary">Info</Badge>;
}

function StatusPill({ st }: { st: Status }) {
  if (st === "resolved")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-success/10 text-success px-2.5 py-0.5 text-xs">
        <CheckCircle2 className="h-3.5 w-3.5" /> Resolved
      </span>
    );
  if (st === "acknowledged")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 text-warning px-2.5 py-0.5 text-xs">
        <Clock3 className="h-3.5 w-3.5" /> Acknowledged
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 text-destructive px-2.5 py-0.5 text-xs">
      <AlertTriangle className="h-3.5 w-3.5" /> Active
    </span>
  );
}

function generatePlan(i: Incident) {
  const risk =
    i.severity === "critical"
      ? "High"
      : i.severity === "warning"
        ? "Medium"
        : "Low";
  const svc = i.service;
  return [
    {
      title: `Rollback latest ${svc} deploy`,
      detail: `Revert to previous stable image for ${svc}.`,
      area: "GitHub/CI",
      status: "pending",
    },
    {
      title: `Scale ${svc} by +2 replicas`,
      detail: "Mitigate traffic while investigating.",
      area: "Kubernetes",
      status: "pending",
    },
    {
      title: `Increase upstream timeout to 8s`,
      detail: "Temporary mitigation until root cause fixed.",
      area: "Config",
      status: "pending",
    },
    {
      title: "Add SLO alert",
      detail: "Create alert for p95 latency > 600ms",
      area: "Prometheus",
      status: "pending",
    },
  ].map((s) => ({ ...s, risk }));
}

export default function Incidents() {
  const { apiClient } = useApi();
  const [tab, setTab] = useState<"active" | "resolved" | "all">("active");
  const [sev, setSev] = useState<"all" | Severity>("all");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Incident | null>(INCIDENTS[0]);
  const [isAcknowledging, setIsAcknowledging] = useState(false);
  const plan = useMemo(
    () => (selected ? generatePlan(selected) : []),
    [selected],
  );

  const handleAcknowledge = async () => {
    try {
      setIsAcknowledging(true);
      const response = await apiClient.forwardPlansToApproved();
      console.log('Plans forwarded:', response);
      // You could add a toast notification here to show success
    } catch (error) {
      console.error('Failed to acknowledge plans:', error);
      // You could add a toast notification here to show error
    } finally {
      setIsAcknowledging(false);
    }
  };

  const filtered = useMemo(() => {
    return INCIDENTS.filter(
      (i) =>
        (tab === "all" ||
          (tab === "resolved"
            ? i.status === "resolved"
            : i.status !== "resolved")) &&
        (sev === "all" || i.severity === sev) &&
        (q.trim() === "" ||
          [i.id, i.title, i.service]
            .join(" ")
            .toLowerCase()
            .includes(q.toLowerCase())),
    );
  }, [tab, sev, q]);

  return (
    <div className="mx-auto w-full max-w-[1400px]">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Incidents</h1>
        <div className="flex items-center gap-2">
          <Button className="gap-2">
            <PlayCircle className="h-4 w-4" /> New Incident
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* Left column: list & filters */}
        <Card className="col-span-12 lg:col-span-6 xl:col-span-7">
          <CardHeader>
            <CardTitle className="text-lg">Browse</CardTitle>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Tabs value={tab} onValueChange={(v) => setTab(v as any)}>
                <TabsList>
                  <TabsTrigger value="active">Active</TabsTrigger>
                  <TabsTrigger value="resolved">Resolved</TabsTrigger>
                  <TabsTrigger value="all">All</TabsTrigger>
                </TabsList>
              </Tabs>
              <ToggleGroup
                type="single"
                value={sev}
                onValueChange={(v) => v && setSev(v as any)}
              >
                <ToggleGroupItem value="all">All Severities</ToggleGroupItem>
                <ToggleGroupItem value="critical">Critical</ToggleGroupItem>
                <ToggleGroupItem value="warning">Warning</ToggleGroupItem>
                <ToggleGroupItem value="info">Info</ToggleGroupItem>
              </ToggleGroup>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search by ID, title, or service"
                  className="pl-9"
                />
              </div>
              <Button variant="secondary">Export</Button>
            </div>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[620px] pr-4">
              <ul className="space-y-3">
                {filtered.map((i) => (
                  <li key={i.id}>
                    <button
                      onClick={() => setSelected(i)}
                      className={`w-full rounded-lg border p-4 text-left transition-colors hover:bg-accent ${selected?.id === i.id ? "ring-2 ring-ring" : ""}`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium truncate">
                              {i.title}
                            </span>
                            <SeverityBadge s={i.severity} />
                            <StatusPill st={i.status} />
                            <span className="rounded-md bg-muted px-2 py-0.5 text-xs">
                              {i.service}
                            </span>
                          </div>
                          <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">
                            AI hypothesis: {i.hypothesis}
                          </p>
                        </div>
                        <div className="shrink-0 text-right">
                          <div className="text-sm text-muted-foreground">
                            {i.updated}
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {i.id}
                          </div>
                        </div>
                      </div>
                    </button>
                  </li>
                ))}
                {filtered.length === 0 && (
                  <li className="rounded-lg border p-6 text-center text-muted-foreground">
                    No incidents match your filters.
                  </li>
                )}
              </ul>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Right column: details */}
        <Card className="col-span-12 lg:col-span-6 xl:col-span-5">
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-3">
              <span>{selected?.title}</span>
              <div className="flex items-center gap-2">
                {selected && <SeverityBadge s={selected.severity} />}{" "}
                {selected && <StatusPill st={selected.status} />}
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {selected ? (
              <div className="space-y-6">
                <section>
                  <h3 className="text-sm font-medium text-muted-foreground">
                    Summary
                  </h3>
                  <p className="mt-2">
                    {selected.hypothesis}. Related service{" "}
                    <span className="font-medium">{selected.service}</span>.
                    Last updated {selected.updated}.
                  </p>
                </section>
                <Separator />
                <section className="space-y-3">
                  <h3 className="text-sm font-medium text-muted-foreground">
                    Actions
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    <Button 
                      className="gap-2" 
                      onClick={handleAcknowledge}
                      disabled={isAcknowledging}
                    >
                      <AlertTriangle className="h-4 w-4" /> 
                      {isAcknowledging ? "Acknowledging..." : "Acknowledge"}
                    </Button>
                    <Button variant="secondary" className="gap-2">
                      <CheckCircle2 className="h-4 w-4" /> Resolve
                    </Button>
                    <Button variant="outline" className="gap-2">
                      <PlayCircle className="h-4 w-4" /> Run Playbook
                    </Button>
                  </div>
                </section>
                <Separator />
                <section>
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-medium text-muted-foreground">
                      Generated Plan
                    </h3>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        onClick={() => {
                          if (!selected) return;
                          const text = plan
                            .map(
                              (s, idx) =>
                                `${idx + 1}. ${s.title} — ${s.detail} [${s.area}]`,
                            )
                            .join("\n");
                          navigator.clipboard?.writeText(text).catch(() => {});
                        }}
                      >
                        Copy
                      </Button>
                      <Button variant="secondary">Regenerate</Button>
                    </div>
                  </div>
                  <ul className="mt-3 space-y-2">
                    {plan.map((s, idx) => (
                      <li key={idx} className="rounded-lg border p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="font-medium">{s.title}</p>
                            <p className="text-sm text-muted-foreground">
                              {s.detail}
                            </p>
                          </div>
                          <div className="flex shrink-0 flex-col items-end gap-1">
                            <span className="rounded-md bg-muted px-2 py-0.5 text-xs">
                              {s.area}
                            </span>
                            <span className="rounded-full bg-warning/10 text-warning px-2 py-0.5 text-xs">
                              Risk: {s.risk}
                            </span>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
                <Separator />
                <section>
                  <h3 className="text-sm font-medium text-muted-foreground">
                    Timeline
                  </h3>
                  <ul className="mt-3 space-y-4">
                    {[
                      {
                        icon: <GitCommit className="h-4 w-4" />,
                        text: `Deploy pushed to ${selected.service}`,
                        at: "26m ago",
                      },
                      {
                        icon: <XCircle className="h-4 w-4" />,
                        text: "Error rate exceeded 5% threshold",
                        at: "22m ago",
                      },
                      {
                        icon: <AlertTriangle className="h-4 w-4" />,
                        text: `${selected.id} opened with correlated signals`,
                        at: "20m ago",
                      },
                    ].map((t, i) => (
                      <li key={i} className="flex items-start gap-3">
                        <div className="mt-0.5 text-muted-foreground">
                          {t.icon}
                        </div>
                        <div>
                          <p className="text-sm">{t.text}</p>
                          <p className="text-xs text-muted-foreground">
                            {t.at}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
                <Separator />
                <section className="space-y-3">
                  <h3 className="text-sm font-medium text-muted-foreground">
                    Assignees
                  </h3>
                  <div className="flex items-center gap-3">
                    <Avatar className="h-8 w-8">
                      <AvatarFallback>JD</AvatarFallback>
                    </Avatar>
                    <Avatar className="h-8 w-8">
                      <AvatarFallback>AL</AvatarFallback>
                    </Avatar>
                  </div>
                </section>
              </div>
            ) : (
              <div className="text-muted-foreground">
                Select an incident from the list to see details.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
