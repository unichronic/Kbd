import { useState, FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Bot, X } from "lucide-react";

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<
    { from: "you" | "kubee"; text: string }[]
  >([
    {
      from: "kubee",
      text: "Hi! I'm KubeeDoo. Ask about incidents, KPIs, or deployments.",
    },
  ]);
  const [query, setQuery] = useState("");

  function sendMessage(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setMessages((m) => [...m, { from: "you", text: q }]);
    setQuery("");
    setTimeout(() => {
      setMessages((m) => [
        ...m,
        {
          from: "kubee",
          text: "I've correlated the spike with a deploy 26 minutes ago to payments-service.",
        },
      ]);
    }, 500);
  }

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {!open ? (
        <button
          aria-label="Open chat"
          onClick={() => setOpen(true)}
          className="flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg hover:opacity-90"
        >
          <Bot className="h-6 w-6" />
        </button>
      ) : (
        <div className="flex h-[480px] w-[360px] sm:w-[400px] flex-col overflow-hidden rounded-xl border bg-background shadow-2xl">
          <div className="flex items-center justify-between border-b p-3">
            <div className="flex items-center gap-2 font-medium">
              <Bot className="h-4 w-4" /> KubeeDoo
            </div>
            <button
              aria-label="Close chat"
              onClick={() => setOpen(false)}
              className="rounded p-1 hover:bg-accent"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col">
            <ScrollArea className="flex-1 p-3 pr-4">
              <div className="space-y-3">
                {messages.map((m, i) => (
                  <div
                    key={i}
                    className={`max-w-[82%] rounded-lg p-3 text-sm ${m.from === "you" ? "ml-auto bg-primary text-primary-foreground" : "bg-muted"}`}
                  >
                    {m.text}
                  </div>
                ))}
              </div>
            </ScrollArea>
            <form onSubmit={sendMessage} className="border-t p-3">
              <div className="flex items-center gap-2">
                <Input
                  placeholder="Ask about health, deploys, incidents..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <Button type="submit" className="gap-2">
                  <Bot className="h-4 w-4" /> Send
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
