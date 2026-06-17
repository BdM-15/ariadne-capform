"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
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
    <main className="mx-auto max-w-5xl p-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-neon-cyan">Ariadne&apos;s Thread</h1>
        <p className="text-sm text-slate-400">Portfolio Pulse — command center triage</p>
      </header>

      {error && <p className="mb-4 text-neon-amber text-sm">{error}</p>}

      {stats && (
        <section className="card mb-6 flex flex-wrap items-center gap-4 text-xs text-slate-400">
          <span className="uppercase tracking-wider text-slate-500">Intel layer</span>
          <span className={intelLive ? "text-neon-lime" : "text-neon-amber"}>
            {intelLive ? "live" : "loading / empty"}
          </span>
          <span>{stats.prime_award_count.toLocaleString()} prime awards</span>
          {stats.subaward_count > 0 && (
            <span>{stats.subaward_count.toLocaleString()} subawards</span>
          )}
          {!intelLive && (
            <span className="text-slate-500">
              Migration in progress — signals appear as rows land in PostgreSQL
            </span>
          )}
        </section>
      )}

      <section className="card mb-8">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm uppercase tracking-wider text-slate-400">Recompete radar</h2>
            <p className="mt-1 text-xs text-slate-500">
              Expiring contracts from USAspending intel — track as capture opportunity
            </p>
          </div>
          {intelLive && (
            <span className="rounded-full border border-neon-cyan/30 px-2 py-1 text-xs text-neon-cyan">
              {signals.length} signals
            </span>
          )}
        </div>

        {!intelLive && (
          <p className="text-sm text-slate-500">
            No intel rows yet. Resume migration in your separate window; pulse refreshes on reload.
          </p>
        )}

        {intelLive && signals.length === 0 && (
          <p className="text-sm text-slate-500">
            Intel loaded but no expiring contracts matched default NAICS in the next 18 months.
          </p>
        )}

        <div className="grid gap-3">
          {signals.map((signal) => {
            const hot = signal.months_to_end != null && signal.months_to_end <= 6;
            return (
              <div
                key={signal.award_key}
                className="rounded-lg border border-edge bg-ink-900/60 p-4 hover:border-neon-magenta/30"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
                      <span className="rounded border border-neon-magenta/40 px-1.5 py-0.5 text-neon-magenta">
                        {signal.kind.replace(/_/g, " ")}
                      </span>
                      {signal.naics_code && (
                        <span className="font-mono text-slate-500">NAICS {signal.naics_code}</span>
                      )}
                    </div>
                    <p className="font-medium text-slate-100">{signal.title || "Unknown recipient"}</p>
                    <p className="mt-1 text-sm text-slate-400">{signal.agency || "Unknown agency"}</p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary shrink-0"
                    disabled={trackingKey === signal.award_key}
                    onClick={() => trackSignal(signal)}
                  >
                    {trackingKey === signal.award_key ? "Tracking…" : "Track opportunity"}
                  </button>
                </div>
                <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500">
                  <span>
                    Ends <span className="text-slate-300">{formatDate(signal.end_date)}</span>
                  </span>
                  <span className={hot ? "text-neon-amber" : "text-slate-400"}>
                    {urgencyLabel(signal.months_to_end)}
                  </span>
                  <span>
                    Obligation <span className="text-slate-300">{formatMoney(signal.obligation)}</span>
                  </span>
                  <span className="font-mono text-slate-600 truncate max-w-xs" title={signal.award_key}>
                    {signal.award_key}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="card mb-8">
        <h2 className="mb-3 text-sm uppercase tracking-wider text-slate-400">New opportunity</h2>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-lg border border-edge bg-ink-900 px-3 py-2 text-sm"
            placeholder="Opportunity name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
          />
          <button type="button" className="btn btn-primary" onClick={create}>
            Create
          </button>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm uppercase tracking-wider text-slate-400">Active opportunities</h2>
        <div className="grid gap-4">
          {opps.length === 0 && (
            <p className="text-sm text-slate-500">No opportunities yet — track a signal or create one manually.</p>
          )}
          {opps.map((o) => (
            <Link key={o.id} href={`/opportunities/${o.id}`} className="card block hover:border-neon-cyan/40">
              <div className="flex items-center justify-between">
                <span className="font-medium">{o.name}</span>
                <span className="text-xs text-slate-400">{o.milestone_gate}</span>
              </div>
              <div className="mt-2 flex gap-3 text-xs text-slate-500">
                <span>{o.capture_phase_band}</span>
                {o.pending_review_count > 0 && (
                  <span className="text-neon-amber">{o.pending_review_count} pending review</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}