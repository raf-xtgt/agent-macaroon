import { useState } from "react";
import type { ArmorStatus } from "../../types";

export interface ImmunizationEntry {
  id: string;
  patternName: string;
  description?: string;
  timestamp?: string;
}

export interface RecentEventEntry {
  time: string;
  action: string;
  decision: "allow" | "deny";
}

interface FleetDefensePanelProps {
  armorStatus: ArmorStatus | null;
  immunizationLog: ImmunizationEntry[];
  violationsCount?: number;
  recentEvents?: RecentEventEntry[];
  apiBaseUrl?: string;
}

export function FleetDefensePanel({
  armorStatus,
  immunizationLog,
  violationsCount = 0,
  recentEvents = [],
  apiBaseUrl,
}: FleetDefensePanelProps) {
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const runtimeCount = armorStatus?.runtime_patterns?.length ?? immunizationLog.length;
  const activeCount = armorStatus?.active_pattern_count ?? (12 + runtimeCount);
  const staticCount = Math.max(12, activeCount - runtimeCount);
  const isArmorEnabled = armorStatus?.model_armor?.enabled ?? true;

  return (
    <div className="border border-slate/30 rounded-lg bg-ink p-4 font-mono text-xs space-y-4">
      {/* Header */}
      <div className="border-b border-slate/20 pb-2">
        <span className="text-slate font-sans uppercase tracking-wider text-[11px] font-semibold block">
          Fleet Defense
        </span>
      </div>

      {/* Stats list */}
      <div className="space-y-1.5 text-xs">
        <div className="flex justify-between items-center">
          <span className="text-slate">Patterns:</span>
          <span className="text-parchment font-medium">
            {staticCount} static + {runtimeCount} runtime
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate">Model Armor:</span>
          <span className="flex items-center gap-1.5">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                isArmorEnabled ? "bg-ledger-green animate-pulse" : "bg-slate/50"
              }`}
            />
            <span className={isArmorEnabled ? "text-ledger-green font-medium" : "text-slate"}>
              {isArmorEnabled ? "enabled" : "disabled"}
            </span>
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate">Agents:</span>
          <span className="text-parchment font-medium">22 registered</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-slate">Violations (24h):</span>
          <span
            className={`font-semibold ${
              violationsCount > 0 ? "text-ledger-red" : "text-parchment"
            }`}
          >
            {violationsCount} {violationsCount > 0 ? "▲" : ""}
          </span>
        </div>
      </div>

      {/* Immunization Section */}
      {immunizationLog.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-slate/20">
          <span className="text-[10px] uppercase font-sans text-shield-blue tracking-wider block font-semibold">
            Immunization
          </span>
          <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
            {immunizationLog.map((entry) => (
              <div
                key={entry.id}
                className="p-3 bg-shield-blue/5 border border-shield-blue/40 rounded space-y-1 text-[11px]"
              >
                <div className="flex items-center justify-between text-shield-blue font-semibold">
                  <span>⛨ Pattern learned:</span>
                  {entry.timestamp && <span className="text-[10px] text-slate">{entry.timestamp}</span>}
                </div>
                <div className="text-parchment font-mono text-xs break-all">
                  {entry.patternName}
                </div>
                {entry.description && (
                  <p className="text-slate/90 italic text-[11px]">&ldquo;{entry.description}&rdquo;</p>
                )}
                <div className="text-shield-blue/90 text-[10px] pt-1 border-t border-shield-blue/20">
                  Next similar attack will be caught at Model Armor, not the gateway.
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Events Mini Feed */}
      {recentEvents.length > 0 && (
        <div className="space-y-1.5 pt-2 border-t border-slate/20">
          <span className="text-[10px] uppercase font-sans text-slate tracking-wider block">
            Recent Events
          </span>
          <div className="space-y-1 max-h-28 overflow-y-auto">
            {recentEvents.slice(-5).reverse().map((ev, idx) => (
              <div key={idx} className="flex items-center justify-between text-[11px] text-slate">
                <span className="shrink-0">{ev.time}</span>
                <span
                  className={`truncate mx-2 ${
                    ev.decision === "deny" ? "text-ledger-red font-semibold" : "text-parchment"
                  }`}
                >
                  {ev.decision === "deny" ? "✕" : "✓"} {ev.action}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Export Defense Profile Action */}
      {apiBaseUrl && (
        <div className="pt-2 border-t border-slate/20 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={async () => {
              if (!apiBaseUrl || isExporting) return;
              setIsExporting(true);
              setExportStatus(null);
              try {
                const res = await fetch(`${apiBaseUrl}/armor/export`);
                if (res.ok) {
                  const data = await res.json();
                  const jsonStr = JSON.stringify(data, null, 2);
                  const blob = new Blob([jsonStr], {
                    type: "application/json",
                  });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = "agent-macaroon-defense-profile.json";
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                  setExportStatus("Downloaded ✓");
                  setTimeout(() => setExportStatus(null), 3000);
                } else {
                  setExportStatus("Export failed");
                }
              } catch {
                setExportStatus("Export failed");
              } finally {
                setIsExporting(false);
              }
            }}
            disabled={isExporting}
            className="px-3 py-1.5 bg-shield-blue/10 border border-shield-blue/40 hover:bg-shield-blue/20 text-shield-blue text-xs font-sans font-medium rounded transition-colors disabled:opacity-40 cursor-pointer flex items-center gap-1.5"
          >
            <span>↓</span>
            <span>
              {isExporting ? "Exporting..." : "Export Defense Profile"}
            </span>
          </button>

          {exportStatus && (
            <span
              className={`text-[11px] font-mono ${
                exportStatus.includes("✓")
                  ? "text-ledger-green"
                  : "text-ledger-red"
              }`}
            >
              {exportStatus}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
