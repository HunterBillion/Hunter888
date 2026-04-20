"use client";

/**
 * /methodologist/scoring — placeholder for L1-L10 scoring config UI.
 *
 * Phase C (2026-04-20). Backend GET/PUT ``/methodologist/scoring-config``
 * готовы; UI для редактирования весов L1-L10 — задача следующей
 * итерации. Stub-страница предотвращает 404 из методологической nav.
 */

import Link from "next/link";
import AuthLayout from "@/components/layout/AuthLayout";
import { Sliders, ArrowLeft, Wrench } from "lucide-react";

export default function MethodologistScoringPage() {
  return (
    <AuthLayout>
      <div className="max-w-3xl mx-auto px-4 md:px-6 py-6">
        <Link
          href="/methodologist"
          className="inline-flex items-center gap-1.5 text-sm mb-5"
          style={{ color: "var(--text-muted)" }}
        >
          <ArrowLeft size={14} />
          К методологу
        </Link>

        <div
          className="rounded-2xl p-6"
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--border-color)",
          }}
        >
          <div className="flex items-start gap-4">
            <div
              className="flex h-12 w-12 items-center justify-center rounded-xl"
              style={{
                background: "#22d3ee22",
                color: "#22d3ee",
                border: "1px solid #22d3ee44",
              }}
            >
              <Sliders size={22} />
            </div>
            <div className="flex-1">
              <h1
                className="text-xl font-bold mb-1"
                style={{ color: "var(--text-primary)" }}
              >
                Скоринг L1-L10
              </h1>
              <p
                className="text-sm"
                style={{ color: "var(--text-muted)" }}
              >
                Конфигурация весов 10 слоёв оценки: script adherence,
                objection handling, communication, anti-patterns, result,
                human factor, narrative, legal accuracy, etc. API-endpoint
                (<code>GET/PUT /methodologist/scoring-config</code>)
                работает, UI редактора в разработке.
              </p>
              <div
                className="mt-4 inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] font-semibold uppercase tracking-widest"
                style={{
                  background: "#facc1518",
                  color: "#facc15",
                  border: "1px solid #facc1544",
                }}
              >
                <Wrench size={12} />
                Скоро
              </div>
            </div>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}
