export default function Loading() {
  return (
    <main className="min-h-screen bg-ink text-parchment flex flex-col items-center p-4 sm:p-6 md:p-10 font-sans">
      <div className="w-full max-w-4xl border border-slate/30 rounded-lg shadow-2xl bg-ink overflow-hidden">
        {/* Header */}
        <header className="px-6 py-4 border-b border-slate/30 flex items-center justify-between">
          <div className="flex items-center gap-2 text-seal-amber font-mono font-semibold tracking-wide">
            <span className="text-xl">⛨</span>
            <span className="text-parchment">agent-macaroon</span>
            <span className="text-slate">·</span>
            <span className="text-slate">replay</span>
          </div>
        </header>

        {/* Search Bar placeholder */}
        <div className="px-6 py-5 border-b border-slate/30 bg-ink/50">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <span className="text-slate font-mono text-sm shrink-0">chain_id</span>
            <div className="h-10 flex-1 bg-slate/10 border border-slate/30 rounded px-3.5 animate-pulse" />
            <div className="h-10 w-24 bg-seal-amber/20 border border-seal-amber/40 rounded animate-pulse" />
          </div>
        </div>

        {/* Loading Content */}
        <div className="py-24 px-6 text-center flex flex-col items-center justify-center space-y-4">
          <div className="font-mono text-sm text-seal-amber flex items-center gap-3">
            <span>Querying spans...</span>
            <span className="text-slate">[■■■■□□□□□□]</span>
          </div>
          <p className="text-xs text-slate font-mono">
            Reconstructing human → agent → tool custody trail...
          </p>
        </div>
      </div>
    </main>
  );
}
