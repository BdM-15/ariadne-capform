"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../lib/api";

type Opp = {
  id: string;
  name: string;
  capture_phase_band: string;
  current_milestone_gate: string;
  pending_review_count: number;
};

export default function PortfolioPulse() {
  const [opps, setOpps] = useState<Opp[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const load = () => api<Opp[]>("/api/opportunities").then(setOpps).catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    await api("/api/opportunities", {
      method: "POST",
      body: JSON.stringify({ name: name.trim() }),
    });
    setName("");
    load();
  };

  return (
    <main className="mx-auto max-w-5xl p-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-neon-cyan">Ariadne&apos;s Thread</h1>
        <p className="text-sm text-slate-400">Portfolio Pulse — command center triage</p>
      </header>

      {error && <p className="mb-4 text-neon-amber text-sm">{error}</p>}

      <section className="card mb-8">
        <h2 className="mb-3 text-sm uppercase tracking-wider text-slate-400">New opportunity</h2>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-lg border border-edge bg-ink-900 px-3 py-2 text-sm"
            placeholder="Opportunity name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button type="button" className="btn btn-primary" onClick={create}>
            Create
          </button>
        </div>
      </section>

      <section className="grid gap-4">
        {opps.map((o) => (
          <Link key={o.id} href={`/opportunities/${o.id}`} className="card block hover:border-neon-cyan/40">
            <div className="flex items-center justify-between">
              <span className="font-medium">{o.name}</span>
              <span className="text-xs text-slate-400">{o.current_milestone_gate}</span>
            </div>
            <div className="mt-2 flex gap-3 text-xs text-slate-500">
              <span>{o.capture_phase_band}</span>
              {o.pending_review_count > 0 && (
                <span className="text-neon-amber">{o.pending_review_count} pending review</span>
              )}
            </div>
          </Link>
        ))}
      </section>
    </main>
  );
}