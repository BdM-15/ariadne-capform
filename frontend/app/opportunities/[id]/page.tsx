"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
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

  return (
    <main className="mx-auto max-w-4xl p-8">
      <Link href="/" className="text-sm text-neon-cyan">
        ← Portfolio Pulse
      </Link>
      <h1 className="mt-4 text-xl font-semibold">Living Briefing Packet</h1>
      <p className="mb-6 text-sm text-slate-400">
        Fields seeded from docs/reference/briefing_packet/BRIEFING_PACKET_DATA_DICTIONARY.md
      </p>

      <section className="space-y-3">
        {packet?.fields.map((f) => (
          <div key={f.field_key} className="card">
            <div className="mb-1 text-xs text-slate-500">{f.field_key}</div>
            <div className="mb-2 text-sm font-medium">{f.field_key.replace(/_/g, " ")}</div>
            <textarea
              className="w-full rounded border border-edge bg-ink-900 p-2 text-sm"
              defaultValue={f.value ?? ""}
              onChange={(e) => setEdits((prev) => ({ ...prev, [f.field_key]: e.target.value }))}
            />
            <div className="mt-2 flex items-center gap-2 text-xs">
              <span className="text-slate-500">{f.status}</span>
              <span className="text-neon-cyan">{f.trust_level}</span>
              <button type="button" className="btn btn-primary ml-auto" onClick={() => saveField(f.field_key)}>
                Submit for review
              </button>
            </div>
          </div>
        ))}
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-sm uppercase tracking-wider text-slate-400">Review queue</h2>
        {reviews
          .filter((r) => r.entity_type === "packet_field_answer")
          .map((r) => (
            <div key={r.id} className="card mb-2 flex items-center justify-between">
              <span className="text-sm">Answer {r.entity_id.slice(0, 8)}…</span>
              <button type="button" className="btn btn-primary" onClick={() => approve(r.id)}>
                Approve
              </button>
            </div>
          ))}
      </section>
    </main>
  );
}