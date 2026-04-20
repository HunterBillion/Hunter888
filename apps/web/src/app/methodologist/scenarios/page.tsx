"use client";

/**
 * /methodologist/scenarios — placeholder hub.
 *
 * Phase C (2026-04-20). Методологическая nav ссылается сюда, но полный
 * CRUD-интерфейс ещё не ready: backend endpoints (POST/PUT/DELETE
 * /methodologist/scenarios/{id}) существуют, UI за ними — отдельная
 * задача. Stub-страница предотвращает 404 из nav и показывает что
 * ожидается.
 */

import Link from "next/link";
import AuthLayout from "@/components/layout/AuthLayout";
import { FileText, ArrowLeft, Wrench } from "lucide-react";

export default function MethodologistScenariosPage() {
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
                background: "#a78bfa22",
                color: "#a78bfa",
                border: "1px solid #a78bfa44",
              }}
            >
              <FileText size={22} />
            </div>
            <div className="flex-1">
              <h1
                className="text-xl font-bold mb-1"
                style={{ color: "var(--text-primary)" }}
              >
                Сценарии тренировок
              </h1>
              <p
                className="text-sm"
                style={{ color: "var(--text-muted)" }}
              >
                CRUD сценариев для методолога. API готов
                (<code>POST/PUT/DELETE /methodologist/scenarios/&#123;id&#125;</code>),
                UI в работе.
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
