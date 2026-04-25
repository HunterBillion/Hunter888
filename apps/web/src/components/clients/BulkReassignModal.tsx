"use client";

import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { X, Loader2, UserCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { useFocusTrap } from "@/hooks/useFocusTrap";
import { logger } from "@/lib/logger";

interface ManagerOption {
  id: string;
  full_name: string;
}

interface BulkReassignModalProps {
  open: boolean;
  clientIds: string[];
  onClose: () => void;
  onDone: () => void;
}

export function BulkReassignModal({ open, clientIds, onClose, onDone }: BulkReassignModalProps) {
  const focusTrapRef = useFocusTrap(open, onClose);
  const [managers, setManagers] = useState<ManagerOption[]>([]);
  const [selectedManager, setSelectedManager] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api.get("/users/?role=manager&limit=100")
      .then((data: ManagerOption[]) => setManagers(Array.isArray(data) ? data : []))
      .catch((err) => { logger.error("Failed to load managers for reassignment:", err); });
  }, [open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedManager) {
      setError("Выберите менеджера");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.post("/clients/bulk/reassign", {
        client_ids: clientIds,
        new_manager_id: selectedManager,
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка переназначения");
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    setSelectedManager("");
    setError(null);
    onClose();
  };

  if (typeof document === "undefined") return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            className="absolute inset-0"
            style={{ background: "var(--overlay-bg, rgba(0,0,0,0.6))", backdropFilter: "blur(4px)" }}
            onClick={handleClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />

          <motion.div
            ref={focusTrapRef}
            role="dialog"
            aria-modal="true"
            aria-label="Переназначение клиентов"
            className="relative w-full max-w-sm rounded-2xl p-6"
            style={{
              background: "var(--bg-secondary, var(--bg-primary))",
              border: "1px solid var(--border-color)",
              boxShadow: "var(--shadow-lg)",
            }}
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
          >
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <UserCheck size={18} style={{ color: "var(--accent)" }} />
                <h2 className="font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
                  Переназначить
                </h2>
              </div>
              <motion.button onClick={handleClose} aria-label="Закрыть" style={{ color: "var(--text-muted)" }} whileTap={{ scale: 0.9 }}>
                <X size={18} />
              </motion.button>
            </div>

            <div className="text-xs mb-4 px-3 py-2 rounded-lg" style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}>
              Выбрано клиентов: <span style={{ color: "var(--accent)" }}>{clientIds.length}</span>
            </div>

            {error && (
              <div className="rounded-lg p-3 mb-4 text-xs" style={{ background: "color-mix(in srgb, var(--danger) 10%, transparent)", color: "var(--danger)" }}>
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium tracking-wide mb-1.5" style={{ color: "var(--text-muted)" }}>МЕНЕДЖЕР *</label>
                <select
                  aria-label="Выберите менеджера"
                  value={selectedManager}
                  onChange={(e) => setSelectedManager(e.target.value)}
                  className="vh-input w-full"
                  required
                >
                  <option value="">— Выберите менеджера —</option>
                  {managers.map((m) => (
                    <option key={m.id} value={m.id}>{m.full_name}</option>
                  ))}
                </select>
              </div>

              <Button type="submit" variant="primary" fluid loading={saving} icon={<UserCheck size={16} />}>
                Переназначить {clientIds.length} клиентов
              </Button>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
