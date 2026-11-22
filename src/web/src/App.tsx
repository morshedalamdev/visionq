import { useState } from "react";
import { Layout, type View } from "./components/Layout";
import { Analytics } from "./features/Analytics";
import { Datasets } from "./features/Datasets";
import { Evidence } from "./features/Evidence";
import { History } from "./features/History";
import { Inspection } from "./features/Inspection";
import { Upload } from "./features/Upload";

export default function App() {
  const [view, setView] = useState<View>("datasets");
  const [runId, setRunId] = useState("");

  return (
    <Layout view={view} onView={setView}>
      {view === "datasets" ? <Datasets /> : null}
      {view === "history" ? (
        <History
          onInspect={(id) => {
            setRunId(id);
            setView("inspection");
          }}
        />
      ) : null}
      {view === "inspection" ? <Inspection initialRunId={runId} /> : null}
      {view === "analytics" ? <Analytics /> : null}
      {view === "upload" ? <Upload /> : null}
      {view === "evidence" ? <Evidence /> : null}
    </Layout>
  );
}
