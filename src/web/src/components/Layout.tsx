import type { ReactNode } from "react";

export type View =
  | "datasets"
  | "history"
  | "inspection"
  | "analytics"
  | "upload"
  | "evidence";

const navigation: Array<{ id: View; label: string }> = [
  { id: "datasets", label: "Dataset quality" },
  { id: "history", label: "Run history" },
  { id: "inspection", label: "Image inspection" },
  { id: "analytics", label: "Analytics" },
  { id: "upload", label: "Image upload" },
  { id: "evidence", label: "Agent evidence" },
];

export function Layout({
  view,
  onView,
  children,
}: {
  view: View;
  onView: (next: View) => void;
  children: ReactNode;
}) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">VQ</span>
          <div>
            <strong>VisionQ</strong>
            <small>Evidence console</small>
          </div>
        </div>
        <nav aria-label="Application navigation">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={view === item.id ? "active" : ""}
              onClick={() => onView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <strong>Local synthetic mode</strong>
          <p>Fixture evidence is never presented as live AI or real-model acceptance.</p>
        </div>
      </aside>
      <main>{children}</main>
    </div>
  );
}
