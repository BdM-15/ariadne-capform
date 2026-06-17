"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, FileText } from "lucide-react";
import { TheseusShell } from "../../../components/theseus-shell";
import { api } from "../../../lib/api";

type Field = {
  field_key: string;
  value: string | null;
  status: string;
  trust_level: string;
  review_state: string | null;
};

type Packet = { opportunity_id: string; fields: Field[] };

type Review = {
  id: string;
  entity_type: string;
  entity_id: string;
  review_state: string;
};

export default function OpportunityWorkspace() {
  const { id } = useParams<{ id: string }>();
  const [packet, setPacket] = useState<Packet | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [edits, setEdits] = useState<Record<string, string>>({});

  const load = async () => {
    setPacket(await api<Packet>(`/api/opportunities/${id}/packet`));
    setReviews(await api<Review[]>("/api/review/pending"));
  };

  useEffect(() => {
    load();
  }, [id]);

  const saveField = async (key: string) => {
    const value = edits[key];
    if (value === undefined) return;
    await api(`/api/opportunities/${id}/packet/${key}`, {
      method: "PATCH",
      body: JSON.stringify({ value }),
    });
    load();
  };

  const approve = async (reviewId: string) => {
    await api(`/api/review/${reviewId}/approve`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    load();
  };

  const pending = reviews.filter((r) => r.entity_type === "packet_field_answer");

  return (
    <TheseusShell subtitle="Living briefing packet" active="pulse">
      <Link href="/" className="topbar-pill inline-flex mb-6">
        <ArrowLeft className="w-4 h-4" />
        Portfolio Pulse
      </Link>

      <div className="mb-7">
        <h1 className="text-3xl font-bold tracking-tight">
          Living Briefing Packet<span className="neon-text">.</span>
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Seeded from{" "}
          <code className="text-neon-cyan font-mono text-xs">docs/reference/briefing_packet/BRIEFING_PACKET_DATA_DICTIONARY.md</code>
        </p>
      </div>

      <section className="space-y-3 mb-8">
        {packet?.fields.map((f) => (
          <div key={f.field_key} className="card card-accent accent-cyan overflow-hidden">
            <div className="px-5 py-3 border-b border-edge flex items-center gap-2">
              <FileText className="w-4 h-4 text-neon-cyan" />
              <div>
                <div className="text-[11px] font-mono uppercase tracking-wider text-slate-500">{f.field_key}</div>
                <div className="text-sm font-semibold">{f.field_key.replace(/_/g, " ")}</div>
              </div>
            </div>
            <div className="p-5">
              <textarea
                className="thread-textarea w-full"
                defaultValue={f.value ?? ""}
                onChange={(e) => setEdits((prev) => ({ ...prev, [f.field_key]: e.target.value }))}
              />
              <div className="mt-3 flex items-center gap-2 text-[11px] font-mono flex-wrap">
                <span className="pill text-slate-500">{f.status}</span>
                <span className="pill border border-neon-cyan/40 text-neon-cyan">{f.trust_level}</span>
                <button type="button" className="btn btn-primary ml-auto" onClick={() => saveField(f.field_key)}>
                  Submit for review
                </button>
              </div>
            </div>
          </div>
        ))}
      </section>

      <section>
        <h2 className="mb-3 text-[11px] font-mono uppercase tracking-wider text-slate-500">Review queue</h2>
        {pending.length === 0 && (
          <div className="card p-5 text-sm text-slate-400">No pending reviews.</div>
        )}
        {pending.map((r) => (
          <div key={r.id} className="card card-hover mb-2 p-4 flex items-center justify-between gap-3">
            <span className="text-sm font-mono text-slate-400">Answer {r.entity_id.slice(0, 8)}…</span>
            <button type="button" className="btn btn-primary" onClick={() => approve(r.id)}>
              <CheckCircle2 className="w-4 h-4" />
              Approve
            </button>
          </div>
        ))}
      </section>
    </TheseusShell>
  );
}