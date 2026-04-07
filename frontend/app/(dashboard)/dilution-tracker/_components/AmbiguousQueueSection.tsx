"use client";

import { useEffect, useMemo, useState } from "react";
import {
  applyAmbiguousActions,
  getReviewMetrics,
  listAmbiguousFilings,
  listReviewedFilings,
  requeueAmbiguousFiling,
  resolveAmbiguousFiling,
  type ApplyAmbiguousActionsResponse,
  type AmbiguousFilingItem,
  type ReviewMetricsResponse,
  type ReviewedFilingItem,
} from "@/lib/dilution-v2-api";

interface AmbiguousQueueSectionProps {
  ticker?: string | null;
}

export function AmbiguousQueueSection({ ticker }: AmbiguousQueueSectionProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<AmbiguousFilingItem[]>([]);
  const [busyAccession, setBusyAccession] = useState<string | null>(null);
  const [selectedAccession, setSelectedAccession] = useState<string | null>(null);
  const [manualJson, setManualJson] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualResponse, setManualResponse] = useState<ApplyAmbiguousActionsResponse | null>(null);
  const [manualBusy, setManualBusy] = useState<"dry_run" | "apply" | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);
  const [lastDryRunFingerprint, setLastDryRunFingerprint] = useState<string | null>(null);
  const [reviewedLoading, setReviewedLoading] = useState(false);
  const [reviewedError, setReviewedError] = useState<string | null>(null);
  const [reviewedItems, setReviewedItems] = useState<ReviewedFilingItem[]>([]);
  const [metrics, setMetrics] = useState<ReviewMetricsResponse | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  const loadAmbiguous = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAmbiguousFilings({
        limit: 100,
        ticker: ticker || undefined,
      });
      setItems(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load queue");
    } finally {
      setLoading(false);
    }
  };

  const loadReviewed = async () => {
    setReviewedLoading(true);
    setReviewedError(null);
    try {
      const data = await listReviewedFilings({
        limit: 50,
        ticker: ticker || undefined,
      });
      setReviewedItems(data.items);
    } catch (err) {
      setReviewedError(err instanceof Error ? err.message : "Failed to load reviewed history");
    } finally {
      setReviewedLoading(false);
    }
  };

  const load = async () => {
    await Promise.all([loadAmbiguous(), loadReviewed(), loadMetrics()]);
  };

  const loadMetrics = async () => {
    setMetricsLoading(true);
    setMetricsError(null);
    try {
      const data = await getReviewMetrics();
      setMetrics(data);
    } catch (err) {
      setMetricsError(err instanceof Error ? err.message : "Failed to load metrics");
    } finally {
      setMetricsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [ticker]);

  const sortedItems = useMemo(
    () =>
      [...items].sort((a, b) => {
        const aTime = new Date(a.filed_at || 0).getTime();
        const bTime = new Date(b.filed_at || 0).getTime();
        return bTime - aTime;
      }),
    [items],
  );

  const handleRequeue = async (accessionNumber: string | null | undefined) => {
    if (!accessionNumber) return;
    setBusyAccession(accessionNumber);
    try {
      await requeueAmbiguousFiling(accessionNumber);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to requeue filing");
    } finally {
      setBusyAccession(null);
    }
  };

  const handleIgnore = async (accessionNumber: string | null | undefined) => {
    if (!accessionNumber) return;
    setBusyAccession(accessionNumber);
    try {
      await resolveAmbiguousFiling(accessionNumber, "ignore", "ignored from queue");
      setItems((prev) => prev.filter((item) => item.accession_number !== accessionNumber));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resolve filing");
    } finally {
      setBusyAccession(null);
    }
  };

  const buildTemplateFromItem = (item: AmbiguousFilingItem) => {
    const template = {
      dry_run: true,
      batch: {
        accession_number: item.accession_number || "",
        ticker: item.ticker || "",
        form_type: item.form_type || "UNKNOWN",
        filing_date: (item.filed_at || new Date().toISOString()).slice(0, 10),
        filing_url:
          typeof item.payload?.filing_url === "string" ? item.payload.filing_url : null,
        agent_model: "human-review-v2",
        agent_summary: "manual review from ambiguous queue",
        actions: [
          {
            action: "log_only",
            reason: "manual review placeholder",
            confidence: "0.90",
            evidence: ["manual_review"],
          },
        ],
      },
    };
    return JSON.stringify(template, null, 2);
  };

  const openManualApply = (item: AmbiguousFilingItem) => {
    setSelectedAccession(item.accession_number || null);
    setManualJson(buildTemplateFromItem(item));
    setManualError(null);
    setManualResponse(null);
    setConfirmApply(false);
    setLastDryRunFingerprint(null);
  };

  const parseManualPayload = (): { parsed: { dry_run: boolean; batch: Record<string, unknown> }; fingerprint: string } => {
    const parsedUnknown = JSON.parse(manualJson);
    if (!parsedUnknown || typeof parsedUnknown !== "object") {
      throw new Error("Invalid payload shape");
    }
    const parsed = parsedUnknown as { dry_run: boolean; batch: Record<string, unknown> };
    if (!parsed.batch || typeof parsed.batch !== "object") {
      throw new Error("batch is required");
    }
    const fingerprint = JSON.stringify({
      batch: parsed.batch,
      manual_json: manualJson.trim(),
    });
    return { parsed, fingerprint };
  };

  const runManual = async (mode: "dry_run" | "apply") => {
    setManualError(null);
    setManualResponse(null);

    let parsed: { dry_run: boolean; batch: Record<string, unknown> };
    let fingerprint: string;
    try {
      const parsedData = parseManualPayload();
      parsed = parsedData.parsed;
      fingerprint = parsedData.fingerprint;
    } catch (err) {
      setManualError(err instanceof Error ? err.message : "Invalid JSON");
      return;
    }

    if (mode === "apply" && !confirmApply) {
      setManualError("Enable confirmation before real apply.");
      return;
    }
    if (mode === "apply" && lastDryRunFingerprint !== fingerprint) {
      setManualError("Run dry_run with this exact payload before real apply.");
      return;
    }

    setManualBusy(mode);
    try {
      const payload = {
        ...parsed,
        dry_run: mode === "dry_run",
      };
      const response = await applyAmbiguousActions(payload);
      setManualResponse(response);
      if (mode === "dry_run") {
        setLastDryRunFingerprint(fingerprint);
      }
      if (!payload.dry_run && selectedAccession) {
        await resolveAmbiguousFiling(
          selectedAccession,
          "accepted_manual_apply",
          "manual apply completed from review panel",
        );
        setItems((prev) =>
          prev.filter((item) => item.accession_number !== selectedAccession),
        );
      }
    } catch (err) {
      setManualError(err instanceof Error ? err.message : "Execution failed");
    } finally {
      setManualBusy(null);
    }
  };

  const manualSummary = useMemo(() => {
    try {
      const parsedUnknown = JSON.parse(manualJson);
      const batch = (parsedUnknown as { batch?: Record<string, unknown> })?.batch || {};
      const actions = Array.isArray(batch.actions) ? batch.actions : [];
      const tickerValue = typeof batch.ticker === "string" ? batch.ticker : "N/A";
      const accessionValue =
        typeof batch.accession_number === "string" ? batch.accession_number : "N/A";
      const formTypeValue = typeof batch.form_type === "string" ? batch.form_type : "N/A";
      return {
        ticker: tickerValue,
        accession: accessionValue,
        formType: formTypeValue,
        actionsCount: actions.length,
      };
    } catch {
      return null;
    }
  }, [manualJson]);

  return (
    <div className="border border-border rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-foreground">Ambiguous Queue</h3>
          <p className="text-xs text-muted-fg">
            Filings that require manual review before write actions.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="px-3 py-1.5 text-xs border border-border rounded hover:bg-surface-hover text-foreground/80"
        >
          Refresh
        </button>
      </div>

      <div className="border border-border rounded p-3">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-medium text-foreground">Pipeline Metrics</h4>
          {metrics?.generated_at && (
            <span className="text-[11px] text-muted-fg">
              Updated {new Date(metrics.generated_at).toLocaleTimeString()}
            </span>
          )}
        </div>
        {metricsError && <p className="text-xs text-red-600">{metricsError}</p>}
        {metricsLoading ? (
          <div className="animate-pulse grid grid-cols-2 gap-2">
            <div className="h-10 bg-muted rounded" />
            <div className="h-10 bg-muted rounded" />
            <div className="h-10 bg-muted rounded" />
            <div className="h-10 bg-muted rounded" />
          </div>
        ) : metrics ? (
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2 border border-border rounded">
              <div className="text-muted-fg">Ambiguous Queue</div>
              <div className="text-foreground font-medium">{metrics.ambiguous_queue_depth}</div>
            </div>
            <div className="p-2 border border-border rounded">
              <div className="text-muted-fg">Reviewed (24h)</div>
              <div className="text-foreground font-medium">{metrics.reviewed_last_24h}</div>
            </div>
            <div className="p-2 border border-border rounded">
              <div className="text-muted-fg">Filings Stream Depth</div>
              <div className="text-foreground font-medium">{metrics.filings_stream_depth}</div>
            </div>
            <div className="p-2 border border-border rounded">
              <div className="text-muted-fg">Reviewed Stream Depth</div>
              <div className="text-foreground font-medium">{metrics.reviewed_stream_depth}</div>
            </div>
            <div className="p-2 border border-border rounded col-span-2">
              <div className="text-muted-fg mb-1">Decisions (24h)</div>
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-foreground">
                {Object.keys(metrics.decisions_last_24h).length === 0 ? (
                  <span className="text-muted-fg">No decisions in last 24h</span>
                ) : (
                  Object.entries(metrics.decisions_last_24h).map(([decision, count]) => (
                    <span key={decision}>
                      {decision}: <span className="font-medium">{count}</span>
                    </span>
                  ))
                )}
              </div>
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted-fg">No metrics available.</p>
        )}
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {loading ? (
        <div className="animate-pulse space-y-2">
          <div className="h-4 bg-muted rounded w-48" />
          <div className="h-12 bg-muted rounded" />
          <div className="h-12 bg-muted rounded" />
        </div>
      ) : sortedItems.length === 0 ? (
        <p className="text-sm text-muted-fg">No ambiguous filings in queue.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 pr-3 text-muted-fg font-medium">Ticker</th>
                <th className="text-left py-2 pr-3 text-muted-fg font-medium">Form</th>
                <th className="text-left py-2 pr-3 text-muted-fg font-medium">Accession</th>
                <th className="text-left py-2 pr-3 text-muted-fg font-medium">Reason</th>
                <th className="text-left py-2 pr-3 text-muted-fg font-medium">Confidence</th>
                <th className="text-right py-2 text-muted-fg font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((item) => {
                const accession = item.accession_number || "";
                const isBusy = busyAccession === accession;
                return (
                  <tr key={item.message_id} className="border-b border-border-subtle">
                    <td className="py-2 pr-3 text-foreground">{item.ticker || "N/A"}</td>
                    <td className="py-2 pr-3 text-foreground">{item.form_type || "N/A"}</td>
                    <td className="py-2 pr-3 text-foreground">{item.accession_number || "N/A"}</td>
                    <td className="py-2 pr-3 text-muted-fg">{item.review_reason || "N/A"}</td>
                    <td className="py-2 pr-3 text-muted-fg">{item.confidence || "N/A"}</td>
                    <td className="py-2 text-right">
                      <div className="inline-flex items-center gap-2">
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => handleRequeue(item.accession_number)}
                          className="px-2 py-1 border border-border rounded hover:bg-surface-hover text-foreground/80 disabled:opacity-50"
                        >
                          Requeue
                        </button>
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => handleIgnore(item.accession_number)}
                          className="px-2 py-1 border border-border rounded hover:bg-surface-hover text-foreground/80 disabled:opacity-50"
                        >
                          Ignore
                        </button>
                        <button
                          type="button"
                          onClick={() => openManualApply(item)}
                          className="px-2 py-1 border border-border rounded hover:bg-surface-hover text-foreground/80"
                        >
                          Manual
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="pt-2 border-t border-border-subtle space-y-3">
        <div>
          <h4 className="text-xs font-medium text-foreground">Manual Apply</h4>
          <p className="text-xs text-muted-fg">
            Use `dry_run` first. Apply only after confirming payload and target instruments.
          </p>
        </div>

        <textarea
          value={manualJson}
          onChange={(event) => {
            setManualJson(event.target.value);
            setLastDryRunFingerprint(null);
          }}
          className="w-full h-56 p-3 text-xs font-mono border border-border rounded bg-surface resize-y"
          placeholder="Select an item with Manual to load a template."
        />

        {manualSummary && (
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2 border border-border rounded">
              <span className="text-muted-fg">Ticker:</span>{" "}
              <span className="text-foreground">{manualSummary.ticker}</span>
            </div>
            <div className="p-2 border border-border rounded">
              <span className="text-muted-fg">Form:</span>{" "}
              <span className="text-foreground">{manualSummary.formType}</span>
            </div>
            <div className="p-2 border border-border rounded col-span-2">
              <span className="text-muted-fg">Accession:</span>{" "}
              <span className="text-foreground">{manualSummary.accession}</span>
              <span className="mx-2 text-muted-fg">-</span>
              <span className="text-muted-fg">Actions:</span>{" "}
              <span className="text-foreground">{manualSummary.actionsCount}</span>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between gap-3">
          <label className="text-xs text-muted-fg flex items-center gap-2">
            <input
              type="checkbox"
              checked={confirmApply}
              onChange={(event) => setConfirmApply(event.target.checked)}
            />
            I confirm this payload is validated for real apply.
          </label>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!manualJson.trim() || manualBusy !== null}
              onClick={() => runManual("dry_run")}
              className="px-3 py-1.5 text-xs border border-border rounded hover:bg-surface-hover text-foreground/80 disabled:opacity-50"
            >
              {manualBusy === "dry_run" ? "Running..." : "Dry Run"}
            </button>
            <button
              type="button"
              disabled={!manualJson.trim() || manualBusy !== null || !confirmApply}
              onClick={() => runManual("apply")}
              className="px-3 py-1.5 text-xs border border-border rounded hover:bg-surface-hover text-foreground/80 disabled:opacity-50"
            >
              {manualBusy === "apply" ? "Applying..." : "Apply"}
            </button>
          </div>
        </div>

        {manualError && <p className="text-xs text-red-600">{manualError}</p>}

        {manualResponse && (
          <div className="border border-border rounded p-3 space-y-2">
            <div className="text-xs text-foreground">
              Result:{" "}
              <span className="font-medium">
                {manualResponse.applied ? "Applied" : "Validated (dry run)"}
              </span>
            </div>
            <div className="text-xs text-muted-fg">
              {manualResponse.changes.length} change(s), {manualResponse.warnings.length} warning(s)
            </div>
            {manualResponse.changes.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-1 pr-3 text-muted-fg font-medium">Action</th>
                      <th className="text-left py-1 pr-3 text-muted-fg font-medium">Result</th>
                      <th className="text-left py-1 text-muted-fg font-medium">Instrument</th>
                    </tr>
                  </thead>
                  <tbody>
                    {manualResponse.changes.map((change, index) => (
                      <tr key={`${change.action}-${index}`} className="border-b border-border-subtle">
                        <td className="py-1 pr-3 text-foreground">{change.action}</td>
                        <td className="py-1 pr-3 text-foreground">{change.result}</td>
                        <td className="py-1 text-muted-fg">{change.instrument_id || "N/A"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="pt-2 border-t border-border-subtle space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-xs font-medium text-foreground">Review History</h4>
            <p className="text-xs text-muted-fg">Recent review decisions for audit traceability.</p>
          </div>
          <button
            type="button"
            onClick={loadReviewed}
            className="px-3 py-1.5 text-xs border border-border rounded hover:bg-surface-hover text-foreground/80"
          >
            Refresh History
          </button>
        </div>

        {reviewedError && <p className="text-xs text-red-600">{reviewedError}</p>}

        {reviewedLoading ? (
          <div className="animate-pulse space-y-2">
            <div className="h-10 bg-muted rounded" />
            <div className="h-10 bg-muted rounded" />
          </div>
        ) : reviewedItems.length === 0 ? (
          <p className="text-xs text-muted-fg">No review history yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 pr-3 text-muted-fg font-medium">Reviewed At</th>
                  <th className="text-left py-2 pr-3 text-muted-fg font-medium">Decision</th>
                  <th className="text-left py-2 pr-3 text-muted-fg font-medium">Ticker</th>
                  <th className="text-left py-2 pr-3 text-muted-fg font-medium">Accession</th>
                  <th className="text-left py-2 text-muted-fg font-medium">Notes</th>
                </tr>
              </thead>
              <tbody>
                {reviewedItems.map((item) => (
                  <tr key={item.message_id} className="border-b border-border-subtle">
                    <td className="py-2 pr-3 text-muted-fg">
                      {item.reviewed_at ? new Date(item.reviewed_at).toLocaleString() : "N/A"}
                    </td>
                    <td className="py-2 pr-3 text-foreground">{item.decision || "N/A"}</td>
                    <td className="py-2 pr-3 text-foreground">
                      {typeof item.payload?.ticker === "string" ? item.payload.ticker : "N/A"}
                    </td>
                    <td className="py-2 pr-3 text-foreground">{item.accession_number || "N/A"}</td>
                    <td className="py-2 text-muted-fg">{item.notes || "N/A"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
