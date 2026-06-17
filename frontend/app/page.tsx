"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Crosshair, FolderPlus, Radar, RefreshCw } from "lucide-react";
import { TheseusShell } from "../components/theseus-shell";
import { api } from "../lib/api";

type Opp = {
  id: string;
  name: string;
  capture_phase_band: string;
  milestone_gate: string;
  urgency_score?: number;
  pending_review_count: number;
};

type IntelSignal = {
  kind: string;
  award_key: string;
  title: string;
  agency: string;
  end_date: string | null;
  months_to_end: number | null;
  obligation: number | null;
  naics_code: string | null;
};

type IntelStats = {
  prime_awards_ready: boolean;
  prime_award_count: number;
  subaward_count: number;
  naics_cache_count: number;
};

type Pulse = {
  opportunities: Opp[];
  intel_signals: IntelSignal[];
  intel_stats: IntelStats;
};

function formatMoney(value: number | null): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: value >= 1_000_000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function urgencyLabel(months: number | null): string {
  if (months == null) return "unknown horizon";
  if (months <= 6) return `${months} mo — hot`;
  if (months <= 12) return `${months} mo — warm`;
  return `${months} mo`;
}

function signalOpportunityName(signal: IntelSignal): string {
  const recipient = signal.title?.trim() || "Unknown recipient";
  const agency = signal.agency?.trim();
  const base = agency ? `${recipient} — ${agency}` : recipient;
  return base.length > 120 ? `${base.slice(0, 117)}…` : base;
}

export default function PortfolioPulse() {
  const [pulse, setPulse] = useState<Pulse | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [trackingKey, setTrackingKey] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Pulse>("/api/portfolio/pulse")
      .then(setPulse)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const create = async () => {
    if (!name.trim()) return;
    try {
      await api("/api/opportunities", {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      });
      setName("");
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const trackSignal = async (signal: IntelSignal) => {
    setTrackingKey(signal.award_key);
    setError("");
    try {
      await api("/api/opportunities", {
        method: "POST",
        body: JSON.stringify({
          name: signalOpportunityName(signal),
          award_key: signal.award_key,
          naics_code: signal.naics_code,
          entry_reason: "intel_signal",
        }),
      });
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setTrackingKey(null);
    }
  };

  const opps = pulse?.opportunities ?? [];
  const signals = pulse?.intel_signals ?? [];
  const stats = pulse?.intel_stats;
  const intelLive = Boolean(stats?.prime_awards_ready && (stats?.prime_award_count ?? 0) > 0);

  return (
    <TheseusShell subtitle="Portfolio pulse" active="pulse">
      <div className="flex items-end justify-between mb-7 flex-wrap gap-4">
        <div>
          <h1 className="text-4xl font-bold tracking-tight">
            Portfolio Pulse<span className="neon-text">.</span>
          </h1>
          <p className="text-base text-slate-400 mt-1">
            Intel layer holds{" "}
            <span className="text-neon-cyan font-mono">{stats?.prime_award_count?.toLocaleString() ?? "—"}</span> prime
            awards ·{" "}
            <span className="text-neon-magenta font-mono">{signals.length}</span> recompete signals ·{" "}
            <span className="text-neon-lime font-mono">{opps.length}</span> active opportunities
          </p>
        </div>
        <div className="flex gap-2.5 flex-wrap">
          <button type="button" className="btn btn-ghost border border-edge" onClick={load}>
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="card card-accent accent-amber p-4 mb-5 text-sm text-neon-amber">{error}</div>
      )}

      {stats && (
        <section className="card card-accent accent-cyan p-5 mb-6 flex flex-wrap items-center gap-4 text-[11px] font-mono uppercase tracking-wider text-slate-500">
          <span className="text-slate-400">Intel layer</span>
          <span className={`pill border ${intelLive ? "border-neon-lime/40 text-neon-lime" : "border-neon-amber/40 text-neon-amber"}`}>
            {intelLive ? "live" : "loading"}
          </span>
          <span>
            <span className="text-neon-cyan">{stats.prime_award_count.toLocaleString()}</span> prime
          </span>
          {stats.subaward_count > 0 && (
            <span>
              <span className="text-neon-magenta">{stats.subaward_count.toLocaleString()}</span> sub
            </span>
          )}
          {!intelLive && <span className="normal-case tracking-normal text-slate-500">Migration window still loading rows</span>}
        </section>
      )}

      <section className="card overflow-hidden mb-6">
        <div className="px-5 py-3 border-b border-edge flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Radar className="w-4 h-4 text-neon-magenta" />
            <h2 className="font-semibold">Recompete radar</h2>
          </div>
          {intelLive && (
            <span className="pill border border-neon-magenta/40 text-neon-magenta">{signals.length} signals</span>
          )}
        </div>
        <div className="p-5 space-y-3">
          {!intelLive && (
            <p className="text-sm text-slate-400">
              No intel rows yet. Resume migration in separate window; hit Refresh when rows land.
            </p>
          )}
          {intelLive && signals.length === 0 && (
            <p className="text-sm text-slate-400">
              Intel loaded — no expiring contracts for default NAICS in next 18 months.
            </p>
          )}
          {signals.map((signal) => {
            const hot = signal.months_to_end != null && signal.months_to_end <= 6;
            return (
              <div
                key={signal.award_key}
                className="card card-hover card-accent accent-magenta p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <span className="pill border border-neon-magenta/40 text-neon-magenta">
                        {signal.kind.replace(/_/g, " ")}
                      </span>
                      {signal.naics_code && (
                        <span className="pill text-slate-500">NAICS {signal.naics_code}</span>
                      )}
                    </div>
                    <p className="font-semibold text-slate-100">{signal.title || "Unknown recipient"}</p>
                    <p className="mt-1 text-sm text-slate-400">{signal.agency || "Unknown agency"}</p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary shrink-0"
                    disabled={trackingKey === signal.award_key}
                    onClick={() => trackSignal(signal)}
                  >
                    <Crosshair className="w-4 h-4" />
                    {trackingKey === signal.award_key ? "Tracking…" : "Track"}
                  </button>
                </div>
                <div className="mt-3 flex flex-wrap gap-4 text-[11px] font-mono text-slate-500">
                  <span>
                    ends <span className="text-slate-300">{formatDate(signal.end_date)}</span>
                  </span>
                  <span className={hot ? "text-neon-amber" : "text-slate-400"}>{urgencyLabel(signal.months_to_end)}</span>
                  <span>
                    obligation <span className="text-slate-300">{formatMoney(signal.obligation)}</span>
                  </span>
                  <span className="truncate max-w-md text-slate-600" title={signal.award_key}>
                    {signal.award_key}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="card card-accent accent-lime p-5 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <FolderPlus className="w-4 h-4 text-neon-lime" />
          <h2 className="font-semibold">New opportunity</h2>
        </div>
        <div className="flex gap-2 flex-wrap">
          <input
            className="thread-input flex-1 min-w-[240px]"
            placeholder="Opportunity name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
          />
          <button type="button" className="btn-hero-cyan inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold text-ink-950" onClick={create}>
            <FolderPlus className="w-4 h-4" />
            Create
          </button>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-[11px] font-mono uppercase tracking-wider text-slate-500">Active opportunities</h2>
        <div className="grid gap-3">
          {opps.length === 0 && (
            <div className="card card-accent accent-amber p-5 text-sm text-slate-400">
              No opportunities yet — track a radar signal or create one manually.
            </div>
          )}
          {opps.map((o) => (
            <Link key={o.id} href={`/opportunities/${o.id}`} className="card card-hover card-accent accent-cyan block p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">{o.name}</span>
                <span className="pill text-slate-500">{o.milestone_gate}</span>
              </div>
              <div className="mt-2 flex gap-3 text-[11px] font-mono text-slate-500">
                <span>{o.capture_phase_band}</span>
                {o.pending_review_count > 0 && (
                  <span className="text-neon-amber">{o.pending_review_count} pending review</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      </section>
    </TheseusShell>
  );
}