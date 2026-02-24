import { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function Badge({ text }) {
  const cls = useMemo(() => {
    const t = (text || "").toLowerCase();
    if (t.includes("fix_pr_created")) return "bg-green-600/20 text-green-300 border-green-600/40";
    if (t.includes("patched")) return "bg-blue-600/20 text-blue-300 border-blue-600/40";
    if (t.includes("analyzed")) return "bg-yellow-600/20 text-yellow-300 border-yellow-600/40";
    if (t.includes("commented")) return "bg-purple-600/20 text-purple-300 border-purple-600/40";
    if (t.includes("error")) return "bg-red-600/20 text-red-300 border-red-600/40";
    return "bg-white/10 text-white/80 border-white/20";
  }, [text]);

  return (
    <span className={`inline-flex items-center px-2 py-1 text-xs border rounded ${cls}`}>
      {text || "unknown"}
    </span>
  );
}

function FindingsTable({ findings }) {
  if (!findings?.length) return <div className="text-white/70">No findings.</div>;

  return (
    <div className="overflow-x-auto border border-white/10 rounded">
      <table className="min-w-full text-sm">
        <thead className="bg-white/5">
          <tr className="text-left">
            <th className="p-3">Category</th>
            <th className="p-3">Severity</th>
            <th className="p-3">File</th>
            <th className="p-3">Line</th>
            <th className="p-3">Title</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f, idx) => (
            <tr key={idx} className="border-t border-white/10">
              <td className="p-3">{f.category}</td>
              <td className="p-3">{f.severity}</td>
              <td className="p-3">{f.file || "-"}</td>
              <td className="p-3">{f.line_hint || "-"}</td>
              <td className="p-3">
                <div className="font-medium">{f.title}</div>
                <div className="text-white/70">{f.recommendation}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [prUrl, setPrUrl] = useState("https://github.com/M10vir/pr-doctor-demo-repo/pull/1");
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [runDetail, setRunDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 2500);
  };

  const loadRuns = async () => {
    const r = await fetch(`${API_BASE}/runs`);
    const data = await r.json();
    setRuns(data);
    if (!selectedRunId && data?.[0]?.id) setSelectedRunId(data[0].id);
  };

  const loadRun = async (id) => {
    if (!id) return;
    const r = await fetch(`${API_BASE}/runs/${id}`);
    const data = await r.json();
    setRunDetail(data);
  };

  useEffect(() => { loadRuns(); }, []);
  useEffect(() => { if (selectedRunId) loadRun(selectedRunId); }, [selectedRunId]);

  const createRun = async () => {
    setBusy(true);
    try {
      const r = await fetch(`${API_BASE}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pr_url: prUrl }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(JSON.stringify(data));
      await loadRuns();
      setSelectedRunId(data.run_id);
      showToast(`Run #${data.run_id} created`);
      return data.run_id;
    } finally {
      setBusy(false);
    }
  };

  const callAction = async (path, payload) => {
    setBusy(true);
    try {
      const r = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(JSON.stringify(data));
      await loadRuns();
      if (payload.run_id) await loadRun(payload.run_id);
      return data;
    } finally {
      setBusy(false);
    }
  };

  const ensureRun = async () => {
    if (selectedRunId) return selectedRunId;
    return await createRun();
  };

  const onAnalyze = async () => {
    const id = await ensureRun();
    await callAction("/analyze-pr", { pr_url: prUrl, run_id: id });
    showToast("Analyzed and saved");
  };

  const onPatch = async () => {
    const id = await ensureRun();
    await callAction("/generate-patch", { pr_url: prUrl, finding_index: 0, run_id: id });
    showToast("Patch generated and saved");
  };

  const onComment = async () => {
    const id = await ensureRun();
    const res = await callAction("/comment-review", { pr_url: prUrl, run_id: id });
    showToast("Comment posted");
    if (res?.comment_url) window.open(res.comment_url, "_blank");
  };

  const onFixPR = async () => {
    const id = await ensureRun();
    const res = await callAction("/open-fix-pr", { pr_url: prUrl, run_id: id });
    showToast("Fix PR created");
    if (res?.fix_pr_url) window.open(res.fix_pr_url, "_blank");
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <div className="max-w-6xl mx-auto p-6 space-y-6">
        <header className="space-y-1">
          <h1 className="text-3xl font-bold">PR Doctor</h1>
          <p className="text-white/70">
            Analyze a GitHub PR, generate a safe patch, post a review comment, and open an auto-fix PR.
          </p>
        </header>

        <div className="bg-white/5 border border-white/10 rounded p-4 space-y-3">
          <div className="flex flex-col md:flex-row gap-3 md:items-center">
            <input
              className="flex-1 bg-black/30 border border-white/10 rounded px-3 py-2 outline-none"
              value={prUrl}
              onChange={(e) => setPrUrl(e.target.value)}
              placeholder="Paste a GitHub PR URL..."
            />
            <button
              disabled={busy}
              onClick={createRun}
              className="px-4 py-2 rounded bg-white/10 hover:bg-white/20 border border-white/10 disabled:opacity-50"
            >
              + New Run
            </button>
          </div>

          <div className="flex flex-wrap gap-2">
            <button disabled={busy} onClick={onAnalyze} className="px-4 py-2 rounded bg-blue-600/20 hover:bg-blue-600/30 border border-blue-600/30">
              Analyze
            </button>
            <button disabled={busy} onClick={onPatch} className="px-4 py-2 rounded bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-600/30">
              Generate Patch
            </button>
            <button disabled={busy} onClick={onComment} className="px-4 py-2 rounded bg-purple-600/20 hover:bg-purple-600/30 border border-purple-600/30">
              Comment Review
            </button>
            <button disabled={busy} onClick={onFixPR} className="px-4 py-2 rounded bg-green-600/20 hover:bg-green-600/30 border border-green-600/30">
              Open Fix PR
            </button>
          </div>

          {toast && <div className="text-sm text-white/80">{toast}</div>}
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          <aside className="md:col-span-1 bg-white/5 border border-white/10 rounded p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">Run History</h2>
              <button onClick={loadRuns} className="text-xs text-white/70 hover:text-white">Refresh</button>
            </div>
            <div className="space-y-2 max-h-[520px] overflow-auto pr-1">
              {runs.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setSelectedRunId(r.id)}
                  className={`w-full text-left p-3 rounded border ${
                    selectedRunId === r.id ? "border-white/30 bg-white/10" : "border-white/10 bg-black/20 hover:bg-white/10"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium">Run #{r.id}</div>
                    <Badge text={r.status} />
                  </div>
                  <div className="text-xs text-white/70 truncate mt-1">{r.pr_title || r.pr_url}</div>
                  <div className="text-[11px] text-white/50 mt-1">{r.created_at}</div>
                </button>
              ))}
              {!runs.length && <div className="text-white/60 text-sm">No runs yet.</div>}
            </div>
          </aside>

          <main className="md:col-span-2 bg-white/5 border border-white/10 rounded p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">Run Details</h2>
              {runDetail?.status && <Badge text={runDetail.status} />}
            </div>

            {!runDetail ? (
              <div className="text-white/70">Select a run to view details.</div>
            ) : (
              <>
                <div className="space-y-1">
                  <div className="text-lg font-semibold">{runDetail.pr_title || "Untitled PR"}</div>
                  <a className="text-blue-300 hover:underline break-all" href={runDetail.pr_url} target="_blank" rel="noreferrer">
                    {runDetail.pr_url}
                  </a>

                  <div className="flex flex-wrap gap-3 text-sm pt-2">
                    {runDetail.comment_url && (
                      <a className="text-purple-300 hover:underline" href={runDetail.comment_url} target="_blank" rel="noreferrer">
                        View Comment
                      </a>
                    )}
                    {runDetail.fix_pr_url && (
                      <a className="text-green-300 hover:underline" href={runDetail.fix_pr_url} target="_blank" rel="noreferrer">
                        View Fix PR
                      </a>
                    )}
                  </div>
                </div>

                <section className="space-y-2">
                  <h3 className="font-semibold">Findings</h3>
                  <FindingsTable findings={runDetail.review?.findings || []} />
                </section>

                <section className="space-y-2">
                  <h3 className="font-semibold">Patch Preview</h3>
                  <div className="text-sm text-white/70">{runDetail.patch?.description || "No patch yet."}</div>
                  <pre className="bg-black/40 border border-white/10 rounded p-3 overflow-auto text-xs whitespace-pre-wrap">
                    {runDetail.patch?.unified_diff || ""}
                  </pre>
                </section>
              </>
            )}
          </main>
        </div>

        <footer className="text-xs text-white/50">Backend: {API_BASE}</footer>
      </div>
    </div>
  );
}
