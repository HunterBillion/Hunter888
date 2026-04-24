"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, X, Trash2, Star } from "lucide-react";
import { api } from "@/lib/api";

interface ReviewItem {
  id: string;
  name: string;
  role: string;
  text: string;
  rating: number;
  approved: boolean;
  deleted: boolean;
  created_at: string;
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          size={14}
          fill={i <= rating ? "var(--warning)" : "transparent"}
          stroke={i <= rating ? "var(--warning)" : "var(--text-muted)"}
          strokeWidth={1.5}
        />
      ))}
    </div>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
}

type FilterMode = "all" | "pending" | "approved";

export function ReviewsAdmin() {
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterMode>("all");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadReviews = useCallback(async () => {
    try {
      setLoading(true);
      const data: ReviewItem[] = await api.get("/reviews/all");
      setReviews(data);
    } catch {
      // silently fail — will show empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReviews();
  }, [loadReviews]);

  const handleApprove = useCallback(async (id: string) => {
    setActionLoading(id);
    try {
      await api.patch(`/reviews/${id}/approve`);
      setReviews((prev) => prev.map((r) => (r.id === id ? { ...r, approved: true } : r)));
    } finally {
      setActionLoading(null);
    }
  }, []);

  const handleReject = useCallback(async (id: string) => {
    setActionLoading(id);
    try {
      await api.patch(`/reviews/${id}/reject`);
      setReviews((prev) => prev.map((r) => (r.id === id ? { ...r, approved: false } : r)));
    } finally {
      setActionLoading(null);
    }
  }, []);

  const handleDelete = useCallback(async (id: string) => {
    setActionLoading(id);
    try {
      await api.delete(`/reviews/${id}`);
      setReviews((prev) => prev.filter((r) => r.id !== id));
    } finally {
      setActionLoading(null);
    }
  }, []);

  const visibleReviews = reviews.filter((r) => !r.deleted);

  const filtered = visibleReviews.filter((r) => {
    if (filter === "pending") return !r.approved;
    if (filter === "approved") return r.approved;
    return true;
  });

  const pendingCount = visibleReviews.filter((r) => !r.approved).length;

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-24 rounded-xl animate-pulse"
            style={{ background: "var(--bg-tertiary)" }}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header + filter */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>
            Отзывы
          </h2>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {visibleReviews.length} всего · {pendingCount} на модерации
          </p>
        </div>

        <div className="flex gap-2">
          {(["all", "pending", "approved"] as FilterMode[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
              style={{
                background: filter === f ? "var(--accent)" : "var(--bg-tertiary)",
                color: filter === f ? "#fff" : "var(--text-secondary)",
                border: `1px solid ${filter === f ? "var(--accent)" : "var(--border-color)"}`,
              }}
            >
              {f === "all" ? "Все" : f === "pending" ? "На модерации" : "Одобренные"}
              {f === "pending" && pendingCount > 0 && (
                <span className="ml-1.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold" style={{ background: "var(--danger)", color: "#fff" }}>
                  {pendingCount}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Reviews list */}
      {filtered.length === 0 ? (
        <div
          className="text-center py-12 rounded-xl"
          style={{ background: "var(--bg-tertiary)", color: "var(--text-muted)" }}
        >
          <p className="text-sm">Нет отзывов</p>
        </div>
      ) : (
        <div className="space-y-3">
          <AnimatePresence mode="popLayout">
            {filtered.map((review) => (
              <motion.div
                key={review.id}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="rounded-xl p-5"
                style={{
                  background: "var(--bg-secondary)",
                  border: `1px solid ${review.approved ? "var(--success)" : "var(--border-color)"}`,
                }}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    {/* Author info */}
                    <div className="flex items-center gap-3 mb-2">
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                        style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}
                      >
                        <span className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                          {review.name ? review.name.charAt(0).toUpperCase() : "?"}
                        </span>
                      </div>
                      <div>
                        <div className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>
                          {review.name || "—"}
                        </div>
                        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                          {review.role}
                        </div>
                      </div>
                      <StarRating rating={review.rating} />
                      <span className="text-xs ml-auto" style={{ color: "var(--text-muted)" }}>
                        {formatDate(review.created_at)}
                      </span>
                    </div>

                    {/* Review text */}
                    <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      &laquo;{review.text}&raquo;
                    </p>

                    {/* Status badge */}
                    <div className="mt-2">
                      <span
                        className="inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
                        style={{
                          background: review.approved ? "var(--success)" : "var(--warning)",
                          color: "#fff",
                          opacity: 0.9,
                        }}
                      >
                        {review.approved ? "Одобрен" : "На модерации"}
                      </span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 flex-shrink-0">
                    {!review.approved && (
                      <button
                        onClick={() => handleApprove(review.id)}
                        disabled={actionLoading === review.id}
                        className="w-8 h-8 rounded-lg flex items-center justify-center transition-all hover:scale-110"
                        style={{ background: "var(--success)", color: "#fff" }}
                        title="Одобрить"
                      >
                        <Check size={16} />
                      </button>
                    )}
                    {review.approved && (
                      <button
                        onClick={() => handleReject(review.id)}
                        disabled={actionLoading === review.id}
                        className="w-8 h-8 rounded-lg flex items-center justify-center transition-all hover:scale-110"
                        style={{ background: "var(--warning)", color: "#fff" }}
                        title="Отклонить"
                      >
                        <X size={16} />
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(review.id)}
                      disabled={actionLoading === review.id}
                      className="w-8 h-8 rounded-lg flex items-center justify-center transition-all hover:scale-110"
                      style={{ background: "var(--danger)", color: "#fff" }}
                      title="Удалить"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
