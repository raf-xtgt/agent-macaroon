import { TimelineTree } from "./components/TimelineTree";
import type { ReplayResponse } from "./types";

interface PageProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function Page(props: PageProps) {
  const searchParams = await props.searchParams;
  const rawChainId = searchParams.chain_id;
  const chainId = typeof rawChainId === "string" ? rawChainId.trim() : "";

  let replayData: ReplayResponse | null = null;
  let isNotFound = false;
  let errorDetail: string | null = null;

  if (chainId) {
    const apiBaseUrl = process.env.AUDIT_API_BASE_URL || "http://localhost:8000";
    try {
      const res = await fetch(
        `${apiBaseUrl}/audit/replay?chain_id=${encodeURIComponent(chainId)}`,
        { cache: "no-store" }
      );

      if (res.status === 404) {
        isNotFound = true;
      } else if (!res.ok) {
        errorDetail = `Backend returned HTTP status ${res.status}`;
      } else {
        replayData = await res.json();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      errorDetail = `Could not connect to Audit API at ${apiBaseUrl} (${msg})`;
    }
  }

  const isBlocked = replayData?.verdict === "blocked";
  const gcpProject = process.env.GOOGLE_CLOUD_PROJECT || "agent-macaroon";

  return (
    <main className="min-h-screen bg-ink text-parchment flex flex-col items-center p-3 sm:p-6 md:p-10 font-sans">
      <div className="w-full max-w-4xl border border-slate/30 rounded-lg shadow-2xl bg-ink overflow-hidden">
        {/* Header */}
        <header className="px-5 sm:px-6 py-4 border-b border-slate/30 flex items-center justify-between">
          <div className="flex items-center gap-2.5 text-seal-amber font-mono font-semibold tracking-wide">
            <span className="text-xl">⛨</span>
            <span className="text-parchment">agent-macaroon</span>
            <span className="text-slate">·</span>
            <span className="text-slate">replay</span>
          </div>
        </header>

        {/* Search Bar — native form GET submission requires zero client JS */}
        <div className="px-5 sm:px-6 py-4 border-b border-slate/30 bg-ink/40">
          <form method="get" className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <label htmlFor="chain_id_input" className="text-slate font-mono text-sm shrink-0">
              chain_id
            </label>
            <input
              id="chain_id_input"
              type="text"
              name="chain_id"
              defaultValue={chainId}
              placeholder="e.g. 7f3a9c02-1e44-4b9a-9c3d-2f0a8e7d5b11"
              required
              className="flex-1 px-3.5 py-2 bg-ink border border-slate/40 rounded text-parchment font-mono text-sm placeholder:text-slate/60 focus:outline-none focus:border-seal-amber focus:ring-1 focus:ring-seal-amber"
            />
            <button
              type="submit"
              className="px-4 py-2 bg-seal-amber/15 border border-seal-amber/50 hover:bg-seal-amber/25 text-seal-amber font-sans font-medium text-sm rounded transition-colors shrink-0 cursor-pointer"
            >
              Replay ▸
            </button>
          </form>
        </div>

        {/* Dynamic State Rendering */}
        {!chainId ? (
          /* 1. Empty State */
          <div className="py-20 px-6 text-center flex flex-col items-center justify-center space-y-4">
            <span className="text-4xl text-seal-amber select-none">⛨</span>
            <div className="space-y-1">
              <h2 className="text-base font-sans font-medium text-parchment">
                Paste a chain_id to replay a task.
              </h2>
              <p className="text-xs font-mono text-slate">
                Every hop, every seal, every decision — in order.
              </p>
            </div>
          </div>
        ) : isNotFound ? (
          /* 2. Not-Found State */
          <div className="py-16 px-6 text-center flex flex-col items-center justify-center space-y-2">
            <p className="font-mono text-sm text-parchment">
              No spans found for chain_id <span className="text-seal-amber">&ldquo;{chainId}&rdquo;</span>.
            </p>
            <p className="font-mono text-xs text-slate">Check the ID and try again.</p>
          </div>
        ) : errorDetail ? (
          /* 3. Error State */
          <div className="py-14 px-6 text-center space-y-2">
            <p className="font-mono text-sm text-ledger-red">Error: {errorDetail}</p>
            <p className="font-sans text-xs text-slate">
              Please verify that the backend service is running and accessible.
            </p>
          </div>
        ) : replayData ? (
          /* 4. Populated Timeline State */
          <div>
            {/* Summary Strip */}
            <div className="px-5 sm:px-6 py-3.5 border-b border-slate/30 bg-ink/70 font-mono text-xs space-y-1.5">
              <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
                <span className="text-slate w-16 shrink-0">human</span>
                <span className="text-parchment truncate">
                  {replayData.human_subject_id || "(anonymous)"}
                </span>
              </div>
              <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
                <span className="text-slate w-16 shrink-0">purpose</span>
                <span className="text-parchment truncate">
                  &ldquo;{replayData.purpose || "(no purpose provided)"}&rdquo;
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-slate pt-0.5">
                <div>
                  started <span className="text-parchment">{replayData.started_at}</span>
                </div>
                <div>
                  hops <span className="text-parchment font-semibold">{replayData.hop_count}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  verdict{" "}
                  {isBlocked ? (
                    <span className="text-ledger-red font-semibold font-mono tracking-wide">
                      ✕ BLOCKED
                    </span>
                  ) : (
                    <span className="text-ledger-green font-semibold font-mono tracking-wide">
                      ✓ ALL OK
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Tree Spans */}
            <div className="px-4 sm:px-6 py-4">
              <TimelineTree spans={replayData.spans} gcpProjectId={gcpProject} chainId={chainId} />
            </div>
          </div>
        ) : null}
      </div>
    </main>
  );
}

