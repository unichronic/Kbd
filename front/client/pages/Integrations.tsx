import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { AlertCircle, Cloud, Github, Slack, Gauge, BarChart3 } from "lucide-react";

 type IntegrationKey =
  | "github"
  | "kubernetes"
  | "slack"
  | "pagerduty"
  | "prometheus"
  | "grafana";

 type Integration = {
  key: IntegrationKey;
  name: string;
  description: string;
  icon: JSX.Element;
  status: "connected" | "disconnected";
 };

 const INTEGRATIONS: Integration[] = [
  { key: "github", name: "GitHub", description: "Sync commits and deployments, correlate to incidents.", icon: <Github className="h-5 w-5" />, status: "disconnected" },
  { key: "kubernetes", name: "Kubernetes", description: "Connect your cluster for metrics and logs.", icon: <Cloud className="h-5 w-5" />, status: "disconnected" },
  { key: "prometheus", name: "Prometheus", description: "Scrape metrics from your cluster/services.", icon: <Gauge className="h-5 w-5" />, status: "disconnected" },
  { key: "grafana", name: "Grafana", description: "Dashboards and visualizations for metrics.", icon: <BarChart3 className="h-5 w-5" />, status: "disconnected" },
  { key: "slack", name: "Slack", description: "Get notifications and chat-ops.", icon: <Slack className="h-5 w-5" />, status: "disconnected" },
  { key: "pagerduty", name: "PagerDuty", description: "Escalations and on-call rotations.", icon: <AlertCircle className="h-5 w-5" />, status: "disconnected" },
 ];

 function IntegrationCard({ item, openConfig }: { item: Integration; openConfig: (k: IntegrationKey)=>void }) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">{item.icon}</div>
          <div>
            <CardTitle className="text-base">{item.name}</CardTitle>
            <p className="text-sm text-muted-foreground">{item.description}</p>
          </div>
        </div>
        <Badge variant={item.status === "connected" ? "default" : "secondary"}>{item.status === "connected" ? "Connected" : "Not connected"}</Badge>
      </CardHeader>
      <CardContent className="mt-auto">
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" onClick={() => openConfig(item.key)}>Configure</Button>
        </div>
      </CardContent>
    </Card>
  );
 }

 function GithubDialog({ onSaved }: { onSaved: () => void }) {
  const [token, setToken] = useState("");
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  return (
    <div className="space-y-4">
      <div className="grid gap-2">
        <Label>Personal Access Token</Label>
        <Input value={token} onChange={(e)=>setToken(e.target.value)} placeholder="ghp_xxx"/>
        <p className="text-xs text-muted-foreground">Required scopes: repo, admin:repo_hook.</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2">
          <Label>Owner/Org</Label>
          <Input value={owner} onChange={(e)=>setOwner(e.target.value)} placeholder="my-org"/>
        </div>
        <div className="grid gap-2">
          <Label>Repository</Label>
          <Input value={repo} onChange={(e)=>setRepo(e.target.value)} placeholder="my-repo"/>
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Webhook Secret</Label>
        <Input placeholder="random-string"/>
      </div>
      <Separator />
      <div className="grid gap-2">
        <Label>Events</Label>
        <Select defaultValue="push">
          <SelectTrigger><SelectValue placeholder="Select"/></SelectTrigger>
          <SelectContent>
            <SelectItem value="push">Push, PR, Releases</SelectItem>
            <SelectItem value="deploy">Deployments</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <DialogFooter>
        <Button onClick={onSaved}>Save</Button>
      </DialogFooter>
    </div>
  );
 }

 function KubernetesDialog({ onSaved }: { onSaved: () => void }) {
  const [mode, setMode] = useState("kubeconfig");
  return (
    <div className="space-y-4">
      <div className="grid gap-2">
        <Label>Auth Method</Label>
        <Select value={mode} onValueChange={setMode}>
          <SelectTrigger><SelectValue/></SelectTrigger>
          <SelectContent>
            <SelectItem value="kubeconfig">Upload kubeconfig</SelectItem>
            <SelectItem value="token">API server + token</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {mode === "kubeconfig" ? (
        <div className="grid gap-2">
          <Label>Kubeconfig (YAML)</Label>
          <Textarea placeholder="Paste contents here" className="min-h-[160px] font-mono"/>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-2"><Label>API Server URL</Label><Input placeholder="https://cluster.example:6443"/></div>
          <div className="grid gap-2"><Label>Bearer Token</Label><Input placeholder="eyJhbGci..."/></div>
          <div className="grid gap-2 col-span-2"><Label>Namespace</Label><Input placeholder="default"/></div>
        </div>
      )}
      <DialogFooter>
        <Button onClick={onSaved}>Save</Button>
      </DialogFooter>
    </div>
  );
 }

 function PrometheusDialog({ onSaved }: { onSaved: () => void }) {
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [job, setJob] = useState("kubernetes-nodes");
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2"><Label>Base URL</Label><Input value={url} onChange={(e)=>setUrl(e.target.value)} placeholder="http://prometheus:9090"/></div>
        <div className="grid gap-2"><Label>Auth Token (optional)</Label><Input value={token} onChange={(e)=>setToken(e.target.value)} placeholder="bearer token"/></div>
      </div>
      <div className="grid gap-2">
        <Label>Default Scrape Job</Label>
        <Select value={job} onValueChange={setJob}>
          <SelectTrigger><SelectValue/></SelectTrigger>
          <SelectContent>
            <SelectItem value="kubernetes-nodes">kubernetes-nodes</SelectItem>
            <SelectItem value="kubernetes-pods">kubernetes-pods</SelectItem>
            <SelectItem value="custom">custom</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <DialogFooter><Button onClick={onSaved}>Save</Button></DialogFooter>
    </div>
  );
 }

 function GrafanaDialog({ onSaved }: { onSaved: () => void }) {
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [dashboard, setDashboard] = useState("k8s");
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2"><Label>Base URL</Label><Input value={url} onChange={(e)=>setUrl(e.target.value)} placeholder="https://grafana.example"/></div>
        <div className="grid gap-2"><Label>API Token</Label><Input value={token} onChange={(e)=>setToken(e.target.value)} placeholder="grafana_pat"/></div>
      </div>
      <div className="grid gap-2">
        <Label>Default Dashboard UID</Label>
        <Input value={dashboard} onChange={(e)=>setDashboard(e.target.value)} placeholder="abcd1234"/>
      </div>
      <DialogFooter><Button onClick={onSaved}>Save</Button></DialogFooter>
    </div>
  );
 }

 function SlackDialog({ onSaved }: { onSaved: () => void }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2"><Label>Bot Token</Label><Input placeholder="xoxb-..."/></div>
        <div className="grid gap-2"><Label>Signing Secret</Label><Input placeholder="xxxx"/></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2"><Label>Incidents Channel</Label><Input placeholder="#incidents"/></div>
        <div className="grid gap-2"><Label>Deploys Channel</Label><Input placeholder="#deploys"/></div>
      </div>
      <DialogFooter><Button onClick={onSaved}>Save</Button></DialogFooter>
    </div>
  );
 }

 function PagerDutyDialog({ onSaved }: { onSaved: () => void }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2"><Label>API Token</Label><Input placeholder="pd_..."/></div>
        <div className="grid gap-2"><Label>Service ID</Label><Input placeholder="PXXXX"/></div>
      </div>
      <div className="grid gap-2"><Label>Escalation Policy</Label><Input placeholder="EPXXXX"/></div>
      <DialogFooter><Button onClick={onSaved}>Save</Button></DialogFooter>
    </div>
  );
 }

 function HostingDialog({ onSaved, provider }: { onSaved: () => void; provider: "netlify" | "vercel" }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2"><Label>Access Token</Label><Input placeholder="token"/></div>
        <div className="grid gap-2"><Label>{provider === "netlify" ? "Site ID" : "Team ID"}</Label><Input placeholder={provider === "netlify" ? "site_xxx" : "team_xxx"}/></div>
      </div>
      <div className="grid gap-2"><Label>Project</Label><Input placeholder="kubee-doo"/></div>
      <DialogFooter><Button onClick={onSaved}>Save</Button></DialogFooter>
    </div>
  );
 }

 function NeonDialog({ onSaved }: { onSaved: () => void }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2"><Label>Connection String</Label><Input placeholder="postgres://..."/></div>
        <div className="grid gap-2"><Label>Database</Label><Input placeholder="kubee"/></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2"><Label>User</Label><Input placeholder="app_user"/></div>
        <div className="grid gap-2"><Label>Schema</Label><Input placeholder="public"/></div>
      </div>
      <DialogFooter><Button onClick={onSaved}>Save</Button></DialogFooter>
    </div>
  );
 }

 function SupabaseDialog({ onSaved }: { onSaved: () => void }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2"><Label>URL</Label><Input placeholder="https://xxx.supabase.co"/></div>
        <div className="grid gap-2"><Label>Anon Key</Label><Input placeholder="public-anon-key"/></div>
      </div>
      <div className="grid gap-2"><Label>Service Role (optional)</Label><Input placeholder="service_role_key"/></div>
      <DialogFooter><Button onClick={onSaved}>Save</Button></DialogFooter>
    </div>
  );
 }

 function ZapierDialog({ onSaved }: { onSaved: () => void }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-2"><Label>Webhook URL</Label><Input placeholder="https://hooks.zapier.com/..."/></div>
      <DialogFooter><Button onClick={onSaved}>Save</Button></DialogFooter>
    </div>
  );
 }

 function BuilderDialog({ onSaved }: { onSaved: () => void }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2"><Label>Public API Key</Label><Input placeholder="publicKey"/></div>
        <div className="grid gap-2"><Label>Space URL</Label><Input placeholder="https://builder.io/api/v2"/></div>
      </div>
      <div className="grid gap-2"><Label>Model Name</Label><Input placeholder="changelogs"/></div>
      <DialogFooter><Button onClick={onSaved}>Save</Button></DialogFooter>
    </div>
  );
 }

 export default function Integrations() {
  const { toast } = useToast();
  const [openKey, setOpenKey] = useState<IntegrationKey | null>(null);

  const onSaved = () => {
    toast({ title: "Saved", description: "Integration configuration updated." });
    setOpenKey(null);
  };

  const openConfig = (k: IntegrationKey) => setOpenKey(k);

  return (
    <div className="mx-auto w-full max-w-[1400px]">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
        <div className="text-sm text-muted-foreground">Tip: Connect GitHub, Kubernetes, Prometheus, Grafana, Slack, and PagerDuty. Use [Open MCP popover] to link external services if available.</div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {INTEGRATIONS.map((it) => (
          <IntegrationCard key={it.key} item={it} openConfig={openConfig} />
        ))}
      </div>

      {/* Dialogs */}
      <Dialog open={openKey === "github"} onOpenChange={(o)=>!o&&setOpenKey(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Connect GitHub</DialogTitle><DialogDescription>Provide repository access and events.</DialogDescription></DialogHeader>
          <GithubDialog onSaved={onSaved} />
        </DialogContent>
      </Dialog>
      <Dialog open={openKey === "kubernetes"} onOpenChange={(o)=>!o&&setOpenKey(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Connect Kubernetes</DialogTitle><DialogDescription>Authenticate to your cluster.</DialogDescription></DialogHeader>
          <KubernetesDialog onSaved={onSaved} />
        </DialogContent>
      </Dialog>
      <Dialog open={openKey === "prometheus"} onOpenChange={(o)=>!o&&setOpenKey(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Connect Prometheus</DialogTitle><DialogDescription>Provide access to your metrics endpoint.</DialogDescription></DialogHeader>
          <PrometheusDialog onSaved={onSaved} />
        </DialogContent>
      </Dialog>
      <Dialog open={openKey === "grafana"} onOpenChange={(o)=>!o&&setOpenKey(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Connect Grafana</DialogTitle><DialogDescription>Enable dashboards and links from incidents.</DialogDescription></DialogHeader>
          <GrafanaDialog onSaved={onSaved} />
        </DialogContent>
      </Dialog>
      <Dialog open={openKey === "slack"} onOpenChange={(o)=>!o&&setOpenKey(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Connect Slack</DialogTitle><DialogDescription>Enable chat-ops and notifications.</DialogDescription></DialogHeader>
          <SlackDialog onSaved={onSaved} />
        </DialogContent>
      </Dialog>
      <Dialog open={openKey === "pagerduty"} onOpenChange={(o)=>!o&&setOpenKey(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Connect PagerDuty</DialogTitle><DialogDescription>Escalate incidents automatically.</DialogDescription></DialogHeader>
          <PagerDutyDialog onSaved={onSaved} />
        </DialogContent>
      </Dialog>
    </div>
  );
 }
