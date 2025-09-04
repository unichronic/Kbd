import { useState } from "react";

export default function Settings() {
  const [email, setEmail] = useState("user@example.com");
  const [workspace, setWorkspace] = useState("Default Workspace");
  const [notifications, setNotifications] = useState(true);

  return (
    <div className="mx-auto max-w-5xl py-8">
      <h1 className="text-2xl font-semibold tracking-tight mb-2">Settings</h1>
      <p className="mb-6 text-muted-foreground">
        Manage your account and workspace preferences.
      </p>

      <div className="space-y-8">
        {/* Profile Section */}
        <section>
          <h2 className="text-lg font-medium mb-2">Profile</h2>
          <div className="flex flex-col gap-2">
            <label className="font-medium">Email</label>
            <input
              className="border rounded px-3 py-2 w-full"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
        </section>

        {/* Workspace Section */}
        <section>
          <h2 className="text-lg font-medium mb-2">Workspace</h2>
          <div className="flex flex-col gap-2">
            <label className="font-medium">Workspace Name</label>
            <input
              className="border rounded px-3 py-2 w-full"
              type="text"
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value)}
            />
          </div>
        </section>

        {/* Notifications Section */}
        <section>
          <h2 className="text-lg font-medium mb-2">Notifications</h2>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={notifications}
              onChange={(e) => setNotifications(e.target.checked)}
            />
            Enable email notifications
          </label>
        </section>
      </div>
    </div>
  );
}
