"use client";

import { useEffect, useState } from "react";
import type {
  ConfidenceLevel,
  EnforcementType,
  RaiType,
  TuneConfig,
  TuneResponse,
} from "../../types";

interface TuneDefensesPanelProps {
  apiBaseUrl: string;
  onTuneApplied?: () => void;
}

const ALL_RAI_TYPES: RaiType[] = [
  "DANGEROUS",
  "HARASSMENT",
  "HATE_SPEECH",
  "SEXUALLY_EXPLICIT",
];

const CONFIDENCE_LEVELS: ConfidenceLevel[] = [
  "HIGH",
  "MEDIUM_AND_ABOVE",
  "LOW_AND_ABOVE",
];

export function TuneDefensesPanel({
  apiBaseUrl,
  onTuneApplied,
}: TuneDefensesPanelProps) {
  const [isExpanded, setIsExpanded] = useState<boolean>(true);
  const [loadingConfig, setLoadingConfig] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  // Form states
  const [piEnabled, setPiEnabled] = useState<boolean>(true);
  const [piConfidence, setPiConfidence] =
    useState<ConfidenceLevel>("LOW_AND_ABOVE");

  const [raiEnabledMap, setRaiEnabledMap] = useState<Record<RaiType, boolean>>({
    DANGEROUS: true,
    HARASSMENT: false,
    HATE_SPEECH: false,
    SEXUALLY_EXPLICIT: false,
  });

  const [raiConfidenceMap, setRaiConfidenceMap] = useState<
    Record<RaiType, ConfidenceLevel>
  >({
    DANGEROUS: "MEDIUM_AND_ABOVE",
    HARASSMENT: "MEDIUM_AND_ABOVE",
    HATE_SPEECH: "HIGH",
    SEXUALLY_EXPLICIT: "HIGH",
  });

  const [enforcementType, setEnforcementType] =
    useState<EnforcementType>("INSPECT_AND_BLOCK");
  const [multiLanguage, setMultiLanguage] = useState<boolean>(true);
  const [maliciousUri, setMaliciousUri] = useState<boolean>(true);
  const [sdpBasic, setSdpBasic] = useState<boolean>(false);

  // Fetch initial config on mount
  useEffect(() => {
    let isDisposed = false;
    async function loadConfig() {
      try {
        setLoadingConfig(true);
        const res = await fetch(`${apiBaseUrl}/armor/config`);
        if (res.ok && !isDisposed) {
          const cfg: TuneConfig = await res.json();
          setPiEnabled(cfg.pi_and_jailbreak_enabled ?? true);
          setPiConfidence(cfg.pi_and_jailbreak_confidence ?? "LOW_AND_ABOVE");

          const newRaiEnabled: Record<RaiType, boolean> = {
            DANGEROUS: false,
            HARASSMENT: false,
            HATE_SPEECH: false,
            SEXUALLY_EXPLICIT: false,
          };
          const newRaiConf: Record<RaiType, ConfidenceLevel> = {
            DANGEROUS: "MEDIUM_AND_ABOVE",
            HARASSMENT: "MEDIUM_AND_ABOVE",
            HATE_SPEECH: "HIGH",
            SEXUALLY_EXPLICIT: "HIGH",
          };

          if (Array.isArray(cfg.rai_filters)) {
            for (const rf of cfg.rai_filters) {
              if (newRaiEnabled[rf.type] !== undefined) {
                newRaiEnabled[rf.type] = true;
                newRaiConf[rf.type] = rf.confidence_level ?? "MEDIUM_AND_ABOVE";
              }
            }
          }

          setRaiEnabledMap(newRaiEnabled);
          setRaiConfidenceMap(newRaiConf);
          setEnforcementType(cfg.enforcement_type ?? "INSPECT_AND_BLOCK");
          setMultiLanguage(cfg.multi_language_detection ?? true);
          setMaliciousUri(cfg.malicious_uri ?? true);
          setSdpBasic(cfg.sdp_basic ?? false);
        }
      } catch {
        // Keep defaults on failure
      } finally {
        if (!isDisposed) {
          setLoadingConfig(false);
        }
      }
    }

    loadConfig();
    return () => {
      isDisposed = true;
    };
  }, [apiBaseUrl]);

  const handleApply = async () => {
    if (saving) return;

    setSaving(true);
    setStatusMessage(null);

    const raiFiltersPayload = ALL_RAI_TYPES.filter(
      (t) => raiEnabledMap[t]
    ).map((t) => ({
      type: t,
      confidence_level: raiConfidenceMap[t],
    }));

    const payload: TuneConfig = {
      pi_and_jailbreak_enabled: piEnabled,
      pi_and_jailbreak_confidence: piConfidence,
      rai_filters: raiFiltersPayload,
      enforcement_type: enforcementType,
      multi_language_detection: multiLanguage,
      malicious_uri: maliciousUri,
      sdp_basic: sdpBasic,
    };

    try {
      const res = await fetch(`${apiBaseUrl}/armor/tune`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data: TuneResponse = await res.json();
        if (data.success) {
          setStatusMessage({
            type: "success",
            text: "✓ Template updated & active",
          });
          if (onTuneApplied) {
            onTuneApplied();
          }
        } else {
          setStatusMessage({
            type: "error",
            text: data.error || "Failed to update Model Armor template",
          });
        }
      } else {
        let errorMsg = `Failed to update template (HTTP ${res.status})`;
        try {
          const errData = await res.json();
          if (errData?.detail) {
            errorMsg =
              typeof errData.detail === "string"
                ? errData.detail
                : JSON.stringify(errData.detail);
          }
        } catch {
          // ignore parsing error
        }
        setStatusMessage({
          type: "error",
          text: errorMsg,
        });
      }
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Network error",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-shield-blue/40 rounded-lg bg-ink p-4 font-mono text-xs space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate/20 pb-2.5">
        <div className="flex items-center gap-2 text-shield-blue font-sans uppercase tracking-wider text-xs font-semibold">
          <span>⛨</span>
          <span>Tune Defenses (Model Armor)</span>
          {loadingConfig && (
            <span className="text-[10px] text-slate font-mono normal-case tracking-normal">
              (loading...)
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="text-slate hover:text-parchment text-[11px] font-mono transition-colors cursor-pointer"
          aria-expanded={isExpanded}
        >
          {isExpanded ? "[▾ collapse]" : "[▸ expand]"}
        </button>
      </div>

      {isExpanded && (
        <div className="space-y-4 pt-1">
          {/* Section 1: PI & Jailbreak */}
          <fieldset className="p-3 border border-slate/20 rounded bg-ink/50 space-y-2.5">
            <legend className="text-parchment font-sans font-medium text-[11px] px-1">
              Prompt Injection & Jailbreak Detection
            </legend>

            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 text-xs">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <span className="text-slate text-[11px]">Confidence:</span>
                {CONFIDENCE_LEVELS.map((level) => (
                  <label
                    key={level}
                    className="flex items-center gap-1 cursor-pointer text-[11px] text-parchment"
                  >
                    <input
                      type="radio"
                      name="piConfidence"
                      value={level}
                      checked={piConfidence === level}
                      onChange={() => setPiConfidence(level)}
                      className="accent-shield-blue focus:ring-shield-blue"
                    />
                    <span className="whitespace-nowrap">{level}</span>
                  </label>
                ))}
              </div>

              <label className="flex items-center gap-2 cursor-pointer text-[11px] text-parchment">
                <input
                  type="checkbox"
                  checked={piEnabled}
                  onChange={(e) => setPiEnabled(e.target.checked)}
                  className="accent-shield-blue focus:ring-shield-blue"
                />
                <span className={piEnabled ? "text-ledger-green" : "text-slate"}>
                  {piEnabled ? "Enabled" : "Disabled"}
                </span>
              </label>
            </div>
          </fieldset>

          {/* Section 2: Responsible AI Filters */}
          <fieldset className="p-3 border border-slate/20 rounded bg-ink/50 space-y-2.5">
            <legend className="text-parchment font-sans font-medium text-[11px] px-1">
              Responsible AI (RAI) Filters
            </legend>

            <div className="flex flex-col gap-2 text-xs">
              {ALL_RAI_TYPES.map((type) => {
                const isChecked = raiEnabledMap[type];
                return (
                  <div
                    key={type}
                    className={`flex items-center justify-between p-2 border rounded transition-colors ${
                      isChecked
                        ? "border-shield-blue/40 bg-shield-blue/5"
                        : "border-slate/20 bg-ink"
                    }`}
                  >
                    <label className="flex items-center gap-2 cursor-pointer text-[11px] text-parchment">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={(e) =>
                          setRaiEnabledMap((prev) => ({
                            ...prev,
                            [type]: e.target.checked,
                          }))
                        }
                        className="accent-shield-blue focus:ring-shield-blue"
                      />
                      <span className="font-semibold">{type}</span>
                    </label>

                    <select
                      value={raiConfidenceMap[type]}
                      onChange={(e) =>
                        setRaiConfidenceMap((prev) => ({
                          ...prev,
                          [type]: e.target.value as ConfidenceLevel,
                        }))
                      }
                      disabled={!isChecked}
                      className="px-2 py-0.5 bg-ink border border-slate/40 rounded text-parchment font-mono text-[10px] focus:outline-none focus:border-shield-blue disabled:opacity-30 cursor-pointer"
                      aria-label={`${type} confidence level`}
                    >
                      {CONFIDENCE_LEVELS.map((lvl) => (
                        <option key={lvl} value={lvl}>
                          {lvl}
                        </option>
                      ))}
                    </select>
                  </div>
                );
              })}
            </div>
          </fieldset>

          {/* Section 3: Enforcement & Additional Safety Options */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            {/* Enforcement Mode */}
            <fieldset className="p-3 border border-slate/20 rounded bg-ink/50 space-y-2">
              <legend className="text-parchment font-sans font-medium text-[11px] px-1">
                Enforcement Mode
              </legend>
              <div className="flex items-center gap-4 text-[11px]">
                <label className="flex items-center gap-1.5 cursor-pointer text-parchment">
                  <input
                    type="radio"
                    name="enforcementType"
                    value="INSPECT_AND_BLOCK"
                    checked={enforcementType === "INSPECT_AND_BLOCK"}
                    onChange={() => setEnforcementType("INSPECT_AND_BLOCK")}
                    className="accent-shield-blue"
                  />
                  <span>Inspect & Block</span>
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer text-parchment">
                  <input
                    type="radio"
                    name="enforcementType"
                    value="INSPECT_ONLY"
                    checked={enforcementType === "INSPECT_ONLY"}
                    onChange={() => setEnforcementType("INSPECT_ONLY")}
                    className="accent-shield-blue"
                  />
                  <span>Inspect Only</span>
                </label>
              </div>
            </fieldset>

            {/* Extra Options */}
            <fieldset className="p-3 border border-slate/20 rounded bg-ink/50 space-y-2">
              <legend className="text-parchment font-sans font-medium text-[11px] px-1">
                Content Sanitization
              </legend>
              <div className="flex flex-col gap-1.5 text-[11px]">
                <label className="flex items-center gap-2 cursor-pointer text-parchment">
                  <input
                    type="checkbox"
                    checked={multiLanguage}
                    onChange={(e) => setMultiLanguage(e.target.checked)}
                    className="accent-shield-blue"
                  />
                  <span>Multi-Language Detection</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-parchment">
                  <input
                    type="checkbox"
                    checked={maliciousUri}
                    onChange={(e) => setMaliciousUri(e.target.checked)}
                    className="accent-shield-blue"
                  />
                  <span>Malicious URI Filter</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-parchment">
                  <input
                    type="checkbox"
                    checked={sdpBasic}
                    onChange={(e) => setSdpBasic(e.target.checked)}
                    className="accent-shield-blue"
                  />
                  <span>Basic SDP (Sensitive Data)</span>
                </label>
              </div>
            </fieldset>
          </div>

          {/* Action Row */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate/20">
            <button
              type="button"
              onClick={handleApply}
              disabled={saving}
              className="px-4 py-1.5 bg-shield-blue/15 border border-shield-blue/50 hover:bg-shield-blue/25 text-shield-blue font-sans font-semibold text-xs rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1.5"
            >
              {saving ? (
                <>
                  <span className="inline-block w-3 h-3 border-2 border-shield-blue/30 border-t-shield-blue rounded-full animate-spin" />
                  <span>Applying Tuning...</span>
                </>
              ) : (
                <>
                  <span>⚡</span>
                  <span>Apply Tuning</span>
                </>
              )}
            </button>

            {statusMessage && (
              <span
                className={`text-[11px] font-mono font-medium ${
                  statusMessage.type === "success"
                    ? "text-ledger-green"
                    : "text-ledger-red"
                }`}
              >
                {statusMessage.text}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
