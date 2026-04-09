"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Search, UserPlus, Users, Check, X, Swords } from "lucide-react";
import { api } from "@/lib/api";
import { UserAvatar } from "@/components/ui/UserAvatar";
import type { FriendItem, FriendSearchResponse } from "@/types";

interface FriendsPanelProps {
  onChallengeSent?: () => void;
}

export function FriendsPanel({ onChallengeSent }: FriendsPanelProps) {
  const [friends, setFriends] = useState<FriendItem[]>([]);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<FriendItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadFriends = async () => {
    setLoading(true);
    try {
      const data = (await api.get("/users/friends?status_filter=all")) as FriendItem[];
      setFriends(Array.isArray(data) ? data : []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFriends();
  }, []);

  useEffect(() => {
    const q = search.trim();
    if (q.length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const data = (await api.get(`/users/friends/search?q=${encodeURIComponent(q)}`)) as FriendSearchResponse;
        setResults(data.items || []);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  const mutate = async (action: () => Promise<void>, id: string) => {
    setBusyId(id);
    try {
      await action();
      await loadFriends();
      if (search.trim().length >= 2) {
        const data = (await api.get(`/users/friends/search?q=${encodeURIComponent(search.trim())}`)) as FriendSearchResponse;
        setResults(data.items || []);
      }
    } finally {
      setBusyId(null);
    }
  };

  const accepted = friends.filter((item) => item.status === "accepted");
  const incoming = friends.filter((item) => item.status === "pending" && item.direction === "incoming");

  return (
    <div className="glass-panel relative overflow-hidden rounded-[24px] p-5">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-24"
        style={{ background: "linear-gradient(180deg, rgba(255,255,255,0.12), transparent)" }}
      />

      <div className="relative flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Users size={18} style={{ color: "var(--accent)" }} />
            <h2 className="t-card-title">Друзья арены</h2>
          </div>
          <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
            Добавляй игроков, принимай заявки и быстро заходи в дуэли.
          </p>
        </div>
        <div className="rounded-full px-3 py-1 text-xs font-mono" style={{ background: "var(--input-bg)", color: "var(--text-secondary)" }}>
          {accepted.length} онлайн-контактов
        </div>
      </div>

      <div className="relative mt-4">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="vh-input pl-10"
          aria-label="Найти игрока по имени или email"
          placeholder="Найти игрока по имени или email"
        />
      </div>

      {search.trim().length >= 2 && (
        <div className="mt-3 space-y-2">
          {searching ? (
            <div className="flex items-center gap-2 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
              <Loader2 size={14} className="animate-spin" /> Поиск игроков...
            </div>
          ) : results.length === 0 ? (
            <div className="rounded-2xl px-4 py-3 text-sm" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
              Совпадений пока нет.
            </div>
          ) : (
            results.map((item) => (
              <div key={item.user_id} className="flex items-center justify-between rounded-2xl px-4 py-3" style={{ background: "var(--input-bg)" }}>
                <div className="flex items-center gap-3">
                  <UserAvatar avatarUrl={item.avatar_url} fullName={item.full_name} size={36} />
                  <div>
                    <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{item.full_name}</div>
                    <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{item.email}</div>
                  </div>
                </div>
                {item.status === "none" ? (
                  <button
                    className="btn-neon px-3 py-2 text-xs"
                    disabled={busyId === item.user_id}
                    aria-label={`Добавить в друзья: ${item.full_name}`}
                    onClick={() => mutate(() => api.post("/users/friends", { user_id: item.user_id }), item.user_id)}
                  >
                    {busyId === item.user_id ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />}
                  </button>
                ) : (
                  <div className="text-xs font-mono uppercase tracking-wider" style={{ color: item.status === "accepted" ? "var(--success)" : "var(--warning)" }}>
                    {item.status === "accepted" ? "В друзьях" : item.direction === "incoming" ? "Входящая" : "Отправлено"}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {incoming.length > 0 && (
        <div className="mt-5">
          <div className="mb-2 text-xs font-mono uppercase tracking-[0.18em]" style={{ color: "var(--warning)" }}>
            Входящие заявки
          </div>
          <div className="space-y-2">
            {incoming.map((item) => (
              <div key={item.friendship_id} className="flex items-center justify-between rounded-2xl px-4 py-3" style={{ background: "rgba(255,215,0,0.08)" }}>
                <div className="flex items-center gap-3">
                  <UserAvatar avatarUrl={item.avatar_url} fullName={item.full_name} size={36} />
                  <div className="text-sm" style={{ color: "var(--text-primary)" }}>{item.full_name}</div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="flex h-9 w-9 items-center justify-center rounded-xl"
                    style={{ background: "rgba(0,255,148,0.15)", color: "var(--success)" }}
                    disabled={busyId === item.friendship_id}
                    aria-label="Принять запрос в друзья"
                    onClick={() => mutate(() => api.post(`/users/friends/${item.friendship_id}/accept`, {}), item.friendship_id)}
                  >
                    <Check size={15} />
                  </button>
                  <button
                    className="flex h-9 w-9 items-center justify-center rounded-xl"
                    style={{ background: "rgba(255,42,109,0.12)", color: "var(--danger)" }}
                    disabled={busyId === item.friendship_id}
                    aria-label="Отклонить запрос в друзья"
                    onClick={() => mutate(() => api.delete(`/users/friends/${item.friendship_id}`), item.friendship_id)}
                  >
                    <X size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-5">
        <div className="mb-2 text-xs font-mono uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>
          Твой круг
        </div>
        {loading ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
            <Loader2 size={16} className="animate-spin" /> Загружаю друзей...
          </div>
        ) : accepted.length === 0 ? (
          <div className="rounded-2xl px-4 py-5 text-sm" style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}>
            Здесь появятся друзья для быстрых PvP-матчей и личных вызовов.
          </div>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {accepted.map((item, idx) => (
              <motion.div
                key={item.friendship_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.04 }}
                className="flex items-center justify-between rounded-2xl px-4 py-3"
                style={{ background: "var(--input-bg)" }}
              >
                <div className="flex items-center gap-3">
                  <UserAvatar avatarUrl={item.avatar_url} fullName={item.full_name} size={36} />
                  <div>
                    <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{item.full_name}</div>
                    <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{item.role}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-mono uppercase tracking-wider"
                    style={{ background: "rgba(99,102,241,0.12)", color: "var(--accent)" }}
                    disabled={busyId === `challenge-${item.user_id}`}
                    aria-label={`Вызвать на дуэль: ${item.full_name}`}
                    onClick={() => mutate(async () => {
                      await api.post(`/pvp/challenge/${item.user_id}`, {});
                      onChallengeSent?.();
                    }, `challenge-${item.user_id}`)}
                  >
                    {busyId === `challenge-${item.user_id}` ? <Loader2 size={12} className="animate-spin" /> : <Swords size={12} />}
                    Вызов
                  </button>
                  <button
                    className="text-xs font-mono uppercase tracking-wider"
                    style={{ color: "var(--danger)" }}
                    disabled={busyId === item.friendship_id}
                    aria-label={`Убрать из друзей: ${item.full_name}`}
                    onClick={() => mutate(() => api.delete(`/users/friends/${item.friendship_id}`), item.friendship_id)}
                  >
                    Убрать
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
