"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Copy, Loader2, Merge, Phone, AlertTriangle, Check,
} from "lucide-react";
import Link from "next/link";
import { BackButton } from "@/components/ui/BackButton";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import AuthLayout from "@/components/layout/AuthLayout";
import { logger } from "@/lib/logger";
import { useNotificationStore } from "@/stores/useNotificationStore";

interface DuplicateClient {
  id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  status: string;
  created_at: string;
  manager_name: string | null;
}

interface DuplicateGroup {
  phone: string;
  clients: DuplicateClient[];
}

export default function DuplicatesPage() {
  const { user } = useAuth();
  const router = useRouter();

  // Only admin/rop
  useEffect(() => {
    if (user && user.role !== "admin" && user.role !== "rop") {
      router.replace("/clients");
    }
  }, [user, router]);

  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [merging, setMerging] = useState<string | null>(null);
  const [mergeTarget, setMergeTarget] = useState<Record<string, string>>({});

  useEffect(() => {
    api.get("/clients/duplicates")
      .then((data: DuplicateGroup[]) => setGroups(Array.isArray(data) ? data : []))
      .catch((err) => { logger.error("Failed to load duplicate clients:", err); })
      .finally(() => setLoading(false));
  }, []);

  const handleMerge = async (phone: string, targetId: string, sourceIds: string[]) => {
    setMerging(phone);
    try {
      for (const sourceId of sourceIds) {
        await api.post(`/clients/${targetId}/merge`, {
          duplicate_id: sourceId,
        });
      }
      // Remove merged group
      setGroups((prev) => prev.filter((g) => g.phone !== phone));
    } catch (err) {
      logger.error("Failed to merge duplicate clients:", err);
      useNotificationStore.getState().addToast({ title: "Ошибка", body: "Не удалось объединить дубликаты", type: "error" });
    }
    setMerging(null);
  };

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="app-page max-w-4xl">
        {/* Header */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <div className="mb-4">
            <BackButton href="/clients" label="К клиентам" />
          </div>

          <div className="flex items-center gap-2">
            <Copy size={20} style={{ color: "var(--accent)" }} />
            <h1 className="font-display text-2xl font-bold tracking-[0.15em]" style={{ color: "var(--text-primary)" }}>
              ДУБЛИКАТЫ
            </h1>
            {groups.length > 0 && (
              <span className="text-xs font-mono px-2 py-0.5 rounded-full ml-2"
                style={{ background: "rgba(245,158,11,0.1)", color: "var(--warning)", border: "1px solid rgba(245,158,11,0.2)" }}
              >
                {groups.length} групп
              </span>
            )}
          </div>
          <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
            Клиенты с одинаковым номером телефона
          </p>
        </motion.div>

        {/* Content */}
        <div className="mt-6 space-y-4">
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="glass-panel p-5 animate-pulse">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="h-4 w-24 rounded bg-[var(--input-bg)]" />
                    <div className="h-3 w-16 rounded bg-[var(--input-bg)]" />
                  </div>
                  <div className="space-y-2">
                    <div className="h-10 rounded-lg bg-[var(--input-bg)]" />
                    <div className="h-10 rounded-lg bg-[var(--input-bg)]" />
                  </div>
                </div>
              ))}
            </div>
          ) : groups.length === 0 ? (
            <div className="text-center py-16">
              <Check size={40} className="mx-auto mb-3" style={{ color: "var(--neon-green, #00FF66)", opacity: 0.4 }} />
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>Дубликатов не найдено</p>
            </div>
          ) : (
            groups.map((group, gi) => (
              <motion.div
                key={group.phone}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: gi * 0.05 }}
                className="glass-panel overflow-hidden"
              >
                {/* Group header */}
                <div className="flex items-center gap-3 px-5 py-3 border-b" style={{ borderColor: "var(--border-color)", background: "rgba(245,158,11,0.04)" }}>
                  <AlertTriangle size={14} style={{ color: "var(--warning)" }} />
                  <div className="flex items-center gap-2">
                    <Phone size={12} style={{ color: "var(--text-muted)" }} />
                    <span className="text-sm font-mono" style={{ color: "var(--text-primary)" }}>{group.phone}</span>
                  </div>
                  <span className="text-xs font-mono ml-auto" style={{ color: "var(--text-muted)" }}>
                    {group.clients.length} записей
                  </span>
                </div>

                {/* Clients in group */}
                <div className="divide-y" style={{ borderColor: "var(--border-color)" }}>
                  {group.clients.map((client) => {
                    const isTarget = mergeTarget[group.phone] === client.id;
                    return (
                      <div
                        key={client.id}
                        className="flex items-center gap-4 px-5 py-3 transition-colors"
                        style={{ background: isTarget ? "var(--accent-muted)" : "transparent" }}
                      >
                        {/* Select as target radio */}
                        <motion.button
                          onClick={() => setMergeTarget((prev) => ({ ...prev, [group.phone]: client.id }))}
                          className="w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0"
                          style={{
                            borderColor: isTarget ? "var(--accent)" : "var(--border-color)",
                            background: isTarget ? "var(--accent)" : "transparent",
                          }}
                          whileTap={{ scale: 0.9 }}
                        >
                          {isTarget && <div className="w-2 h-2 rounded-full bg-white" />}
                        </motion.button>

                        <div className="flex-1 min-w-0">
                          <Link href={`/clients/${client.id}`} className="text-sm font-medium hover:underline" style={{ color: "var(--text-primary)" }}>
                            {client.full_name}
                          </Link>
                          <div className="flex items-center gap-3 mt-0.5">
                            {client.email && (
                              <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{client.email}</span>
                            )}
                            <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{client.status}</span>
                            {client.manager_name && (
                              <span className="text-xs" style={{ color: "var(--text-muted)" }}>{client.manager_name}</span>
                            )}
                          </div>
                        </div>

                        <span className="text-xs font-mono shrink-0" style={{ color: "var(--text-muted)" }}>
                          {new Date(client.created_at).toLocaleDateString("ru-RU")}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Merge action */}
                <div className="px-5 py-3 border-t flex items-center justify-between" style={{ borderColor: "var(--border-color)" }}>
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {mergeTarget[group.phone]
                      ? "Остальные записи будут объединены в выбранную"
                      : "Выберите основную запись"}
                  </span>
                  <motion.button
                    onClick={() => {
                      const target = mergeTarget[group.phone];
                      if (!target) return;
                      const sourceIds = group.clients.filter((c) => c.id !== target).map((c) => c.id);
                      handleMerge(group.phone, target, sourceIds);
                    }}
                    disabled={!mergeTarget[group.phone] || merging === group.phone}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
                    style={{
                      background: mergeTarget[group.phone] ? "var(--accent-muted)" : "var(--input-bg)",
                      color: mergeTarget[group.phone] ? "var(--accent)" : "var(--text-muted)",
                      border: `1px solid ${mergeTarget[group.phone] ? "var(--accent)" : "var(--border-color)"}`,
                      opacity: mergeTarget[group.phone] ? 1 : 0.5,
                    }}
                    whileTap={{ scale: 0.97 }}
                  >
                    {merging === group.phone ? <Loader2 size={12} className="animate-spin" /> : <Merge size={12} />}
                    Объединить
                  </motion.button>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>
    </div>
    </AuthLayout>
  );
}
