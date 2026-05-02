"use client";

/**
 * CharacterPicker — Issue #169.
 *
 * Surfaces the custom-character presets the player can pick before
 * starting a PvP/PvE duel. Backend: GET ``/api/pvp/characters/available``
 * (PR #142) returns ``own`` (creator's presets) + ``shared`` (other
 * users' is_shared=true presets, deduped against ``own``).
 *
 * The picker is purely additive — clicking "Случайный" (default)
 * preserves the legacy random-archetype behaviour. Selecting a
 * preset card highlights it; the parent forwards the chosen
 * ``character_id`` to ``queue.join`` / ``pve.accept`` payloads.
 *
 * Component contract
 * ------------------
 *  * ``selectedId`` — ``null`` = random (default), string = picked
 *    custom character id.
 *  * ``onPick(id | null)`` — fires whenever the selection changes.
 *  * ``disabled`` — set during ``queueStatus === "searching"`` so
 *    the player can't change their pick mid-search.
 */

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface AvailableCharacter {
  id: string;
  name: string;
  archetype: string;
  profession?: string;
  difficulty: number;
  description?: string;
  is_own: boolean;
  is_shared: boolean;
  play_count?: number;
  avg_score?: number;
}

interface AvailableCharactersResponse {
  own: AvailableCharacter[];
  shared: AvailableCharacter[];
  total: number;
}

interface Props {
  selectedId: string | null;
  onPick: (id: string | null) => void;
  disabled?: boolean;
}

export function CharacterPicker({ selectedId, onPick, disabled }: Props) {
  const [data, setData] = useState<AvailableCharactersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get<AvailableCharactersResponse>("/pvp/characters/available?limit=50")
      .then((res) => {
        if (cancelled) return;
        setData(res);
      })
      .catch((err) => {
        if (cancelled) return;
        logger.warn("[CharacterPicker] load failed:", err);
        setError("Не удалось загрузить список персонажей");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const ownCount = data?.own.length ?? 0;
  const sharedCount = data?.shared.length ?? 0;
  const total = (data?.total ?? ownCount + sharedCount + 1);

  return (
    <section
      aria-labelledby="char-picker-title"
      className="px-3 py-3"
      style={{
        background: "var(--bg-panel)",
        border: "2px solid var(--accent)",
        outlineOffset: -2,
        boxShadow: "3px 3px 0 0 var(--accent)",
      }}
    >
      <header className="flex items-center justify-between mb-2">
        <h3
          id="char-picker-title"
          className="font-pixel"
          style={{
            color: "var(--text-primary)",
            fontSize: 14,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Кто будет твоим клиентом?
        </h3>
        <span
          className="font-pixel"
          style={{ color: "var(--text-muted)", fontSize: 12, letterSpacing: "0.1em" }}
        >
          {total} опций
        </span>
      </header>

      {/* Random / default card always present */}
      <div className="mb-3">
        <PickerCard
          title="Случайный"
          subtitle="Случайный архетип из системного пула"
          selected={selectedId === null}
          disabled={disabled}
          onClick={() => onPick(null)}
        />
      </div>

      {loading && (
        <p className="font-pixel" style={{ color: "var(--text-muted)", fontSize: 12 }}>
          Загрузка персонажей…
        </p>
      )}

      {error && !loading && (
        <p
          role="alert"
          className="font-pixel"
          style={{ color: "var(--danger)", fontSize: 12 }}
        >
          {error}
        </p>
      )}

      {!loading && !error && data && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Column
            label="Мои клиенты"
            empty="Создай в /training через CharacterBuilder"
            cards={data.own}
            selectedId={selectedId}
            onPick={onPick}
            disabled={disabled}
          />
          <Column
            label="Поделились коллеги"
            empty="Пока никто не поделился"
            cards={data.shared}
            selectedId={selectedId}
            onPick={onPick}
            disabled={disabled}
          />
        </div>
      )}
    </section>
  );
}

function Column({
  label,
  empty,
  cards,
  selectedId,
  onPick,
  disabled,
}: {
  label: string;
  empty: string;
  cards: AvailableCharacter[];
  selectedId: string | null;
  onPick: (id: string | null) => void;
  disabled?: boolean;
}) {
  return (
    <div>
      <h4
        className="font-pixel mb-2"
        style={{
          color: "var(--accent)",
          fontSize: 12,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </h4>
      {cards.length === 0 ? (
        <p className="font-pixel" style={{ color: "var(--text-muted)", fontSize: 12 }}>
          {empty}
        </p>
      ) : (
        <div className="space-y-2">
          {cards.map((c) => (
            <PickerCard
              key={c.id}
              title={c.name}
              subtitle={[
                c.archetype,
                c.profession,
                `сложность ${c.difficulty}`,
                c.play_count ? `${c.play_count} игр` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
              description={c.description}
              selected={selectedId === c.id}
              disabled={disabled}
              onClick={() => onPick(c.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function PickerCard({
  title,
  subtitle,
  description,
  selected,
  disabled,
  onClick,
}: {
  title: string;
  subtitle?: string;
  description?: string;
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={disabled}
      whileHover={disabled ? undefined : { x: -1, y: -1 }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      aria-pressed={selected}
      className="w-full text-left font-pixel"
      style={{
        padding: "10px 12px",
        background: selected ? "var(--accent-muted)" : "var(--bg-secondary)",
        border: `2px solid ${selected ? "var(--accent)" : "var(--border-color)"}`,
        outlineOffset: -2,
        boxShadow: selected
          ? "3px 3px 0 0 var(--accent)"
          : "2px 2px 0 0 var(--border-color)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.65 : 1,
      }}
    >
      <div
        style={{
          color: selected ? "var(--accent)" : "var(--text-primary)",
          fontSize: 14,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          marginBottom: 2,
        }}
      >
        {title}
      </div>
      {subtitle && (
        <div
          style={{
            color: "var(--text-muted)",
            fontSize: 11,
            letterSpacing: "0.04em",
          }}
        >
          {subtitle}
        </div>
      )}
      {description && (
        <div
          style={{
            color: "var(--text-secondary, var(--text-muted))",
            fontSize: 12,
            marginTop: 4,
            lineHeight: 1.4,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {description}
        </div>
      )}
    </motion.button>
  );
}
