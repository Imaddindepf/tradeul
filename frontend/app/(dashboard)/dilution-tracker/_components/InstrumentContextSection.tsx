"use client";

import { useState } from "react";
import type { InstrumentContextResponse } from "@/lib/dilution-v2-api";

interface Props {
  context: InstrumentContextResponse | null;
  loading: boolean;
  error: string | null;
  fontClass?: string;
}

// ─── formatting ───────────────────────────────────────────────────────────────
function fmtAmt(v?: number | null): string {
  if (v == null) return "-";
  const abs = Math.abs(v);
  if (abs >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000)     return `$${(v / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000)         return `$${(v / 1_000).toFixed(0)}K`;
  return `$${Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}
function fmtNum(v?: number | null): string {
  if (v == null) return "-";
  return Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 });
}
function fmtDate(d?: string | null): string {
  if (!d) return "-";
  try {
    const dt = new Date(d + "T12:00:00");
    return `${dt.toLocaleString("en-US", { month: "short" })} ${dt.getDate()} '${String(dt.getFullYear()).slice(2)}`;
  } catch { return d; }
}
function prettify(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, m => m.toUpperCase());
}

// ─── key figure per type ─────────────────────────────────────────────────────
function keyFigure(inst: InstrumentContextResponse["instruments"][number]): string {
  const d = inst.details as Record<string, unknown> || {};
  switch (inst.offering_type) {
    case "Warrant":
      return `${fmtNum(Number(d.remaining_warrants || 0))} os.`;
    case "Convertible Note":
    case "Convertible Preferred":
      return `${fmtNum(Number(d.remaining_shares_converted || 0))} sh.`;
    case "ATM":
      return `${fmtAmt(Number(d.remaining_atm_capacity || 0))} rem.`;
    case "Equity Line":
      return `${fmtAmt(Number(d.remaining_el_capacity || 0))} rem.`;
    case "Shelf":
      return `${fmtAmt(Number(d.current_raisable_amount || 0))} raisable`;
    default:
      return inst.last_update_date ? fmtDate(inst.last_update_date) : "-";
  }
}

// ─── expiry / maturity date ───────────────────────────────────────────────────
function expiryDate(inst: InstrumentContextResponse["instruments"][number]): string {
  const d = inst.details as Record<string, unknown> || {};
  const raw = (d.expiration_date ?? d.maturity_date ?? d.agreement_end_date) as string | undefined;
  if (!raw) return "-";
  try {
    const dt = new Date(raw + "T12:00:00");
    return `${dt.toLocaleString("en-US", { month: "short" })} ${dt.getDate()} '${String(dt.getFullYear()).slice(2)}`;
  } catch { return raw; }
}

// ─── detail pairs per type ────────────────────────────────────────────────────
const DETAIL_ORDER: Record<string, string[]> = {
  Warrant: ["remaining_warrants","exercise_price","total_warrants_issued","known_owners","underwriter","price_protection","pp_clause","issue_date","exercisable_date","expiration_date"],
  "Convertible Note": ["remaining_shares_converted","remaining_principal","conversion_price","total_shares_converted","total_principal","known_owners","underwriter","price_protection","issue_date","convertible_date","maturity_date"],
  "Convertible Preferred": ["remaining_shares_converted","remaining_dollar_amount","conversion_price","total_shares_converted","total_dollar_amount","known_owners","underwriter","price_protection","issue_date","convertible_date","maturity_date"],
  "Equity Line": ["remaining_el_capacity","total_el_capacity","agreement_start_date","agreement_end_date"],
  ATM: ["remaining_atm_capacity","total_atm_capacity","atm_limited_by_baby_shelf","remaining_capacity_without_baby_shelf","placement_agent","agreement_start_date"],
  Shelf: ["current_raisable_amount","total_shelf_capacity","baby_shelf_restriction","total_amount_raised","outstanding_shares","float","effect_date","expiration_date"],
  "S-1 Offering": ["status","anticipated_deal_size","final_deal_size","s1_filing_date"],
};

const DETAIL_LABELS: Record<string, string> = {
  remaining_warrants: "Remaining Warrants",
  exercise_price: "Exercise Price",
  total_warrants_issued: "Total Warrants Issued",
  known_owners: "Known Owners",
  underwriter: "Underwriter",
  price_protection: "Price Protection",
  pp_clause: "PP Clause",
  issue_date: "Issue Date",
  exercisable_date: "Exercisable Date",
  expiration_date: "Expiration Date",
  remaining_shares_converted: "Remaining Conv. Shares",
  remaining_principal: "Remaining Principal",
  conversion_price: "Conversion Price",
  total_shares_converted: "Total Shares When Converted",
  total_principal: "Total Principal",
  convertible_date: "Convertible Date",
  maturity_date: "Maturity Date",
  remaining_dollar_amount: "Remaining Amount",
  total_dollar_amount: "Total Amount",
  remaining_el_capacity: "Remaining EL Capacity",
  total_el_capacity: "Total EL Capacity",
  agreement_start_date: "Agreement Start",
  agreement_end_date: "Agreement End",
  remaining_atm_capacity: "Remaining ATM Capacity",
  total_atm_capacity: "Total ATM Capacity",
  atm_limited_by_baby_shelf: "Baby Shelf Limited",
  remaining_capacity_without_baby_shelf: "Remaining w/o Baby Shelf",
  placement_agent: "Placement Agent",
  current_raisable_amount: "Current Raisable",
  total_shelf_capacity: "Total Shelf Capacity",
  baby_shelf_restriction: "Baby Shelf",
  total_amount_raised: "Total Raised",
  outstanding_shares: "Outstanding Shares",
  float: "Float",
  effect_date: "Effect Date",
  anticipated_deal_size: "Anticipated Deal Size",
  final_deal_size: "Final Deal Size",
  s1_filing_date: "S-1 Filing Date",
};

function fmtDetailVal(key: string, val: unknown): string {
  if (val == null || val === "") return "-";
  if (typeof val === "boolean") return val ? "Yes" : "No";
  if (typeof val === "number") {
    if (key.includes("price") || key.includes("amount") || key.includes("capacity") ||
        key.includes("principal") || key.includes("raisable") || key.includes("raised") || key.includes("size")) {
      return fmtAmt(val);
    }
    return fmtNum(val);
  }
  const s = String(val);
  // date-like
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return fmtDate(s);
  return s;
}

// ─── status colour ────────────────────────────────────────────────────────────
function statusClass(s: string): string {
  const l = s.toLowerCase();
  if (l === "registered") return "text-green-600 dark:text-green-400";
  if (l.includes("terminat") || l.includes("expir") || l.includes("pric") || l.includes("withdrawn")) return "text-muted-foreground";
  return "text-amber-600 dark:text-amber-400";
}

// ─── is expired? ──────────────────────────────────────────────────────────────
const INACTIVE = new Set(["terminated", "expired", "priced", "withdrawn"]);
function isExpired(inst: InstrumentContextResponse["instruments"][number]): boolean {
  if (INACTIVE.has(inst.reg_status.toLowerCase())) return true;
  const d = inst.details as Record<string, unknown> || {};
  const raw = (d.expiration_date ?? d.maturity_date) as string | undefined;
  if (raw) {
    try { if (new Date(raw) < new Date()) return true; } catch { /* ignore */ }
  }
  return false;
}

// ─── single instrument row ────────────────────────────────────────────────────
function InstRow({
  inst,
  fontClass,
}: {
  inst: InstrumentContextResponse["instruments"][number];
  fontClass: string;
}) {
  const [open, setOpen] = useState(false);
  const d = inst.details as Record<string, unknown> || {};
  const order = DETAIL_ORDER[inst.offering_type] || [];
  const pairs = Object.entries(d)
    .filter(([k]) => k !== "instrument_id")
    .sort(([a], [b]) => {
      const ai = order.indexOf(a), bi = order.indexOf(b);
      if (ai < 0 && bi < 0) return a.localeCompare(b);
      if (ai < 0) return 1;
      if (bi < 0) return -1;
      return ai - bi;
    });

  const expired = isExpired(inst);

  return (
    <>
      {/* summary row */}
      <tr
        className={`border-b border-border-subtle hover:bg-muted/[0.07] cursor-pointer transition-colors ${open ? "bg-muted/[0.06]" : ""} ${expired ? "opacity-40" : ""}`}
        onClick={() => setOpen(o => !o)}
      >
        <td className="px-2 py-[5px] text-[10px] text-muted-foreground whitespace-nowrap w-20">
          {inst.offering_type.replace("Convertible ", "Conv. ")}
        </td>
        <td className="px-2 py-[5px] text-[11px] max-w-[140px] truncate">
          {inst.security_name || inst.offering_type}
        </td>
        <td className="px-2 py-[5px] text-[11px] font-medium text-right whitespace-nowrap tabular-nums">
          {keyFigure(inst)}
        </td>
        <td className="px-2 py-[5px] text-[10px] text-muted-foreground text-right whitespace-nowrap tabular-nums">
          {expiryDate(inst)}
        </td>
        <td className={`px-2 py-[5px] text-[10px] text-right whitespace-nowrap w-16 ${statusClass(inst.reg_status)}`}>
          {inst.reg_status === "Not Registered" ? "Not Reg." : inst.reg_status}
        </td>
      </tr>

      {/* expanded detail */}
      {open && (
        <tr className="border-b border-border-subtle">
          <td colSpan={5} className="p-0">
            <div className="grid grid-cols-2 border-t border-border-subtle bg-muted/[0.025]">
              {pairs.map(([key, val]) => (
                <div
                  key={key}
                  className={`flex justify-between gap-2 px-3 py-[4px] text-[10px] border-b border-r border-border-subtle last:border-b-0 ${fontClass}`}
                >
                  <span className="text-muted-foreground shrink-0">
                    {DETAIL_LABELS[key] || prettify(key)}
                  </span>
                  <span className={`text-right font-medium break-words max-w-[50%] ${key === "pp_clause" ? "text-muted-foreground" : ""}`}>
                    {fmtDetailVal(key, val)}
                  </span>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ─── main export ──────────────────────────────────────────────────────────────
export function InstrumentContextSection({ context, loading, error, fontClass = "" }: Props) {
  const [showExpired, setShowExpired] = useState(false);

  if (loading) {
    return (
      <div className={`${fontClass} animate-pulse px-2 py-2`}>
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-7 bg-muted/40 rounded mb-1" />
        ))}
      </div>
    );
  }
  if (error) return <div className="px-2 py-2 text-[11px] text-muted-foreground">{error}</div>;
  if (!context) return <div className="px-2 py-2 text-[11px] text-muted-foreground">No instrument data.</div>;

  const active  = context.instruments.filter(i => !isExpired(i));
  const expired = context.instruments.filter(i =>  isExpired(i));

  return (
    <table className={`w-full border-collapse ${fontClass}`}>
      <thead>
        <tr className="border-b border-border bg-background sticky top-0 z-10">
          <th className="px-2 py-[4px] text-left text-[9px] font-medium uppercase tracking-wider text-muted-foreground/60 w-20">Type</th>
          <th className="px-2 py-[4px] text-left text-[9px] font-medium uppercase tracking-wider text-muted-foreground/60">Name</th>
          <th className="px-2 py-[4px] text-right text-[9px] font-medium uppercase tracking-wider text-muted-foreground/60">Key Figure</th>
          <th className="px-2 py-[4px] text-right text-[9px] font-medium uppercase tracking-wider text-muted-foreground/60">Exp / Mat</th>
          <th className="px-2 py-[4px] text-right text-[9px] font-medium uppercase tracking-wider text-muted-foreground/60 w-16">Status</th>
        </tr>
      </thead>
      <tbody>
        {active.map(inst => (
          <InstRow key={inst.id} inst={inst} fontClass={fontClass} />
        ))}

        {/* inactive separator */}
        {expired.length > 0 && (
          <>
            <tr
              className="border-b border-border-subtle cursor-pointer hover:bg-muted/5"
              onClick={() => setShowExpired(o => !o)}
            >
              <td colSpan={5} className="px-2 py-[4px] text-[9px] uppercase tracking-wider text-muted-foreground/40 select-none">
                Inactive / Expired ({expired.length}) {showExpired ? "−" : "+"}
              </td>
            </tr>
            {showExpired && expired.map(inst => (
              <InstRow key={inst.id} inst={inst} fontClass={fontClass} />
            ))}
          </>
        )}
      </tbody>
    </table>
  );
}
