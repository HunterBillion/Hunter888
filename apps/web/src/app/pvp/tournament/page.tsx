"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Trophy, Clock, Swords, Zap, UserPlus, Shield } from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import { useTournamentStore } from "@/stores/useTournamentStore";
import { useNotificationStore } from "@/stores/useNotificationStore";
import AuthLayout from "@/components/layout/AuthLayout";
import { BracketView } from "@/components/pvp/BracketView";
import { useSound } from "@/hooks/useSound";
import { AppIcon } from "@/components/ui/AppIcon";

const PODIUM_COLORS = ["var(--rank-gold)", "var(--rank-silver)", "var(--rank-bronze)"];
const PODIUM_EMOJI = ["\uD83E\uDD47", "\uD83E\uDD48", "\uD83E\uDD49"];

export default function TournamentPage() {
  const router = useRouter();
  const { playSound } = useSound();
  const { tournament, leaderboard, bracket, loading, fetchActive, fetchBracket, registerForBracket } = useTournamentStore();
  const [registering, setRegistering] = useState(false);

  useEffect(() => {
    fetchActive();
  }, [fetchActive]);

  // If bracket format, also fetch the bracket data
  useEffect(() => {
    if (tournament?.format === "bracket" && tournament.id) {
      fetchBracket(tournament.id);
    }
  }, [tournament?.format, tournament?.id, fetchBracket]);

  // Countdown to tournament end
  const timeRemaining = useMemo(() => {
    if (!tournament?.week_end) return null;
    const end = new Date(tournament.week_end).getTime();
    const now = Date.now();
    const diff = end - now;
    if (diff <= 0) return "Завершён";
    const days = Math.floor(diff / 86400000);
    const hours = Math.floor((diff % 86400000) / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);
    if (days > 0) return `${days}д ${hours}ч`;
    if (hours > 0) return `${hours}ч ${mins}мин`;
    return `${mins} мин`;
  }, [tournament?.week_end]);

  // Registration countdown for bracket format
  const regTimeRemaining = useMemo(() => {
    if (!tournament?.registration_end) return null;
    const end = new Date(tournament.registration_end).getTime();
    const now = Date.now();
    const diff = end - now;
    if (diff <= 0) return null;
    const hours = Math.floor(diff / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);
    if (hours > 0) return `${hours}ч ${mins}мин`;
    return `${mins} мин`;
  }, [tournament?.registration_end]);

  const isBracket = tournament?.format === "bracket";

  const handleRegister = async () => {
    if (!tournament) return;
    setRegistering(true);
    try {
      await registerForBracket(tournament.id);
      playSound("match_start", 0.4);
      fetchBracket(tournament.id);
      useNotificationStore.getState().addToast({
        title: "Регистрация успешна",
        body: "Вы добавлены в сетку турнира.",
        type: "success",
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось зарегистрироваться";
      useNotificationStore.getState().addToast({
        title: "Ошибка регистрации",
        body: msg,
        type: "error",
      });
    } finally {
      setRegistering(false);
    }
  };

  return (
    <AuthLayout>
    <div className="min-h-screen" style={{ background: "var(--bg-primary)" }}>
      {/* Header */}
      <div
        className="sticky top-0 z-40 px-4 py-3"
        style={{
          background: "var(--glass-bg)",
          backdropFilter: "blur(20px)",
          borderBottom: "1px solid var(--glass-border)",
        }}
      >
        <div className="mx-auto flex max-w-3xl items-center gap-3">
          <BackButton href="/pvp" label="К арене" />
          {isBracket ? (
            <Swords size={18} style={{ color: "var(--accent)" }} />
          ) : (
            <Trophy size={18} style={{ color: "var(--warning)" }} />
          )}
          <h1 className="font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
            {isBracket ? "Турнир на выбывание" : "Турнир недели"}
          </h1>
          {timeRemaining && (
            <div className="ml-auto">
              <span className="status-badge status-badge--warning">
                <Clock size={13} />
                {timeRemaining}
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="mx-auto max-w-3xl p-4 space-y-6">
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block h-6 w-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: "var(--accent)" }} />
          </div>
        )}

        {!loading && !tournament && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-panel rounded-2xl text-center py-16 px-6"
          >
            <Trophy size={48} className="mx-auto mb-4" style={{ color: "var(--text-muted)" }} />
            <h2 className="text-xl font-display mb-2" style={{ color: "var(--text-primary)" }}>
              Нет активного турнира
            </h2>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Следующий турнир начнётся в понедельник. Приходите позже!
            </p>
          </motion.div>
        )}

        {!loading && tournament && (
          <>
            {/* Tournament banner */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glow-card"
            >
              <div className="glow-card-inner rounded-2xl p-6 text-center">
                <div className="text-3xl mb-2">{isBracket ? "\u2694\uFE0F" : "\uD83C\uDFC6"}</div>
                <h2 className="font-display text-xl font-bold mb-1" style={{ color: isBracket ? "var(--accent)" : "var(--warning)" }}>
                  {tournament.title}
                </h2>
                {tournament.description && (
                  <p className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
                    {tournament.description}
                  </p>
                )}
                <div className="flex items-center justify-center gap-3 flex-wrap">
                  {isBracket ? (
                    <>
                      <span className="badge-neon">
                        <Swords size={13} /> Плей-офф
                      </span>
                      <span className="status-badge status-badge--online">
                        Раунд: {tournament.current_round || "Регистрация"}
                      </span>
                      {regTimeRemaining && (
                        <span className="status-badge status-badge--warning">
                          <Clock size={9} /> Рег: {regTimeRemaining}
                        </span>
                      )}
                    </>
                  ) : (
                    <>
                      <span className="badge-neon">
                        <Shield size={13} /> Попыток: {tournament.max_attempts}
                      </span>
                      <span className="status-badge status-badge--warning">
                        <Clock size={9} /> {timeRemaining}
                      </span>
                    </>
                  )}
                </div>

                {/* Prizes */}
                <div className="flex items-center justify-center gap-6 mt-5">
                  {[
                    { place: 1, xp: tournament.bonus_xp_first, emoji: PODIUM_EMOJI[0], color: PODIUM_COLORS[0] },
                    { place: 2, xp: tournament.bonus_xp_second, emoji: PODIUM_EMOJI[1], color: PODIUM_COLORS[1] },
                    { place: 3, xp: tournament.bonus_xp_third, emoji: PODIUM_EMOJI[2], color: PODIUM_COLORS[2] },
                  ].map(({ place, xp, emoji, color }) => (
                    <div key={place} className="text-center">
                      <div className={`text-xl ${place === 1 ? "neon-pulse" : ""}`}><AppIcon emoji={emoji} size={24} /></div>
                      <div className="stat-chip mt-1">
                        <span className="stat-chip__value" style={{ color }}>+{xp}</span>
                        <span className="stat-chip__label">XP</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>

            {/* Action button */}
            {isBracket ? (
              regTimeRemaining ? (
                <motion.button
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleRegister}
                  disabled={registering}
                  className="btn-neon btn-neon--green w-full flex items-center justify-center gap-2 py-4 text-lg font-bold rounded-xl"
                >
                  <UserPlus size={20} />
                  {registering ? "Регистрация..." : "Зарегистрироваться"}
                </motion.button>
              ) : null
            ) : (
              <motion.button
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => {
                  playSound("match_start", 0.4);
                  router.push("/pvp?tab=knowledge&autostart=tournament");
                }}
                className="btn-neon w-full flex items-center justify-center gap-2 py-4 text-lg font-bold rounded-xl"
              >
                <Zap size={20} />
                Участвовать в турнире
              </motion.button>
            )}

            {/* Bracket view (knockout format) */}
            {isBracket && bracket && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
              >
                <BracketView bracket={bracket} />
              </motion.div>
            )}

            {/* Leaderboard (classic format) */}
            {!isBracket && (
              <>
                {/* Podium — top 3 */}
                {leaderboard.length >= 3 && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 }}
                    className="glass-panel rounded-2xl p-6"
                  >
                    <h3 className="text-xs font-mono tracking-wider mb-4 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
                      <Trophy size={12} style={{ color: "var(--warning)" }} />
                      ПОДИУМ
                    </h3>
                    <div className="flex items-end justify-center gap-4">
                      <PodiumSlot entry={leaderboard[1]} place={2} height="h-24" />
                      <PodiumSlot entry={leaderboard[0]} place={1} height="h-32" />
                      <PodiumSlot entry={leaderboard[2]} place={3} height="h-20" />
                    </div>
                  </motion.div>
                )}

                {/* Full leaderboard */}
                <div className="glass-panel rounded-2xl p-5">
                  <h3 className="text-xs font-mono tracking-wider mb-3 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
                    <Swords size={12} style={{ color: "var(--accent)" }} />
                    ЛИДЕРБОРД ({leaderboard.length} участников)
                  </h3>
                  <div className="space-y-2">
                    {leaderboard.map((entry, i) => (
                      <motion.div
                        key={entry.user_id}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.05 }}
                        className="flex items-center gap-3 rounded-xl px-4 py-3"
                        style={{
                          background: entry.is_podium
                            ? `rgba(${i === 0 ? "255,215,0" : i === 1 ? "192,192,192" : "205,127,50"},0.06)`
                            : "var(--glass-bg)",
                          border: entry.is_podium
                            ? `1px solid rgba(${i === 0 ? "255,215,0" : i === 1 ? "192,192,192" : "205,127,50"},0.15)`
                            : "1px solid var(--glass-border)",
                        }}
                      >
                        <span className="w-8 text-center font-mono text-sm font-bold" style={{ color: "var(--text-muted)" }}>
                          {entry.is_podium ? <AppIcon emoji={PODIUM_EMOJI[entry.rank - 1]} size={16} /> : `#${entry.rank}`}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                            {entry.full_name}
                          </p>
                          <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                            {entry.attempts} попыток
                          </p>
                        </div>
                        <div className="text-right">
                          <div className="stat-chip">
                            <span className="stat-chip__value" style={{ color: entry.is_podium ? PODIUM_COLORS[entry.rank - 1] : "var(--accent)" }}>
                              {Math.round(entry.best_score)}
                            </span>
                            <span className="stat-chip__label">очков</span>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
    </AuthLayout>
  );
}

function PodiumSlot({
  entry,
  place,
  height,
}: {
  entry: { full_name: string; best_score: number; rank: number };
  place: number;
  height: string;
}) {
  return (
    <div className="flex flex-col items-center w-24">
      <div className="text-xs font-medium mb-1 truncate w-full text-center" style={{ color: "var(--text-secondary)" }}>
        {entry.full_name.split(" ")[0]}
      </div>
      <div className={`text-xl mb-1 ${place === 1 ? "neon-pulse" : ""}`}><AppIcon emoji={PODIUM_EMOJI[place - 1]} size={24} /></div>
      <div
        className={`${height} w-full rounded-t-xl flex items-center justify-center`}
        style={{
          background: `rgba(${place === 1 ? "255,215,0" : place === 2 ? "192,192,192" : "205,127,50"},0.12)`,
          border: `1px solid rgba(${place === 1 ? "255,215,0" : place === 2 ? "192,192,192" : "205,127,50"},0.25)`,
          borderBottom: "none",
        }}
      >
        <span className="font-mono text-lg font-bold" style={{ color: PODIUM_COLORS[place - 1] }}>
          {Math.round(entry.best_score)}
        </span>
      </div>
    </div>
  );
}
