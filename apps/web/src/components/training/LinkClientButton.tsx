"use client";

import { useEffect, useRef, useState } from "react";
import { Link2, Loader2, User as UserIcon } from "lucide-react";
import { toast } from "sonner";
import { ApiError, api } from "@/lib/api";

interface LinkedClient {
  id: string;
  full_name: string;
}

interface ClientListItem {
  id: string;
  full_name: string;
  phone: string | null;
}

interface ClientListPayload {
  items: ClientListItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

interface LinkClientResponsePayload {
  session_id: string;
  real_client_id: string;
  real_client_name: string;
}

interface LinkClientButtonProps {
  sessionId: string;
  initialLinkedClient?: LinkedClient | null;
  variant?: "chat" | "call";
  disabled?: boolean;
  onLinked?: (client: LinkedClient) => void;
}

/**
 * BUG B7 — UX gap. The paperclip endpoint
 * (POST /api/training/sessions/{id}/attachments) refuses uploads with
 * HTTP 400 ("Сессия не привязана к CRM-клиенту") when
 * `TrainingSession.real_client_id` is NULL. Until this component existed,
 * users had no way to perform that link from the training screen and the
 * paperclip was effectively dead. This button:
 *
 *   - shows a static chip when the session is already linked,
 *   - shows a "Привязать клиента" button + popover otherwise.
 *
 * The popover lists CRM clients owned by the current manager via
 * GET /api/clients and writes the selected one back through
 * PATCH /api/training/sessions/{id}/link-client.
 */
export function LinkClientButton({
  sessionId,
  initialLinkedClient = null,
  variant = "chat",
  disabled = false,
  onLinked,
}: LinkClientButtonProps) {
  const isCall = variant === "call";
  const [linked, setLinked] = useState<LinkedClient | null>(initialLinkedClient);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [clients, setClients] = useState<ClientListItem[]>([]);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  // Sync external prop changes (e.g. parent re-fetches the session).
  useEffect(() => {
    if (initialLinkedClient) setLinked(initialLinkedClient);
  }, [initialLinkedClient]);

  // If the parent didn't pre-resolve the linked client, look it up once
  // so the chip persists across page reloads. We fetch the session result
  // and, when it carries `real_client_id`, ask the clients list for the
  // matching name. Failure is silent — the user will still see the
  // "Привязать клиента" button.
  useEffect(() => {
    if (initialLinkedClient || linked) return;
    let cancelled = false;
    (async () => {
      try {
        const sessionResult = await api.get<{
          session?: { real_client_id?: string | null };
        }>(`/training/sessions/${sessionId}`);
        const realClientId = sessionResult.session?.real_client_id;
        if (cancelled || !realClientId) return;
        try {
          const client = await api.get<ClientListItem>(`/clients/${realClientId}`);
          if (cancelled || !client?.id) return;
          setLinked({ id: client.id, full_name: client.full_name });
        } catch {
          // Fall back to id-only chip — name lookup may 404 if the user
          // lost ownership of the client after the session started.
          if (!cancelled) {
            setLinked({ id: realClientId, full_name: "Клиент CRM" });
          }
        }
      } catch {
        // Session lookup failed — keep the unlinked button rendered.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, initialLinkedClient, linked]);

  // Close popover on outside click.
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const loadClients = async () => {
    setLoading(true);
    try {
      const data = await api.get<ClientListPayload>("/clients?per_page=100");
      setClients(data.items || []);
    } catch (err) {
      const msg = err instanceof ApiError || err instanceof Error
        ? err.message
        : "Не удалось загрузить список клиентов";
      toast.error("Ошибка", { description: msg });
    } finally {
      setLoading(false);
    }
  };

  const openPopover = () => {
    if (disabled) return;
    setOpen(true);
    void loadClients();
  };

  const handleSelect = async (client: ClientListItem) => {
    setSubmitting(client.id);
    try {
      const result = await api.patch<LinkClientResponsePayload>(
        `/training/sessions/${sessionId}/link-client`,
        { real_client_id: client.id },
      );
      const next: LinkedClient = {
        id: result.real_client_id,
        full_name: result.real_client_name,
      };
      setLinked(next);
      onLinked?.(next);
      setOpen(false);
      toast.success("Клиент привязан", { description: next.full_name });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.detail as
          | { message?: string; real_client_id?: string }
          | null;
        toast.error(
          "Сессия уже привязана к другому клиенту",
          { description: detail?.message || err.message },
        );
      } else {
        const msg = err instanceof ApiError || err instanceof Error
          ? err.message
          : "Не удалось привязать клиента";
        toast.error("Ошибка", { description: msg });
      }
    } finally {
      setSubmitting(null);
    }
  };

  // ── Linked state: chip is now a button — clicking opens the same popover
  // so the user can SWAP the linked client. Backend PATCH was made
  // swap-allowed in 2026-05-04 (γ); previously a different real_client_id
  // returned 409 with no UI path to recover.
  // ── Unlinked state: "Привязать клиента" button + popover ────────────────
  return (
    <div ref={popoverRef} className="relative shrink-0">
      <button
        type="button"
        disabled={disabled}
        onClick={openPopover}
        aria-label={linked ? "Сменить CRM-клиента" : "Привязать CRM-клиента к сессии"}
        // NEW-7: explicit 1-2 sentence tooltip in Russian — users were
        // asking "что делает кнопка Привязать клиента". Browsers render
        // <title> on hover; that's enough for a quick answer without a
        // popover dependency.
        title={linked
          ? `CRM-клиент: ${linked.full_name}. Нажмите, чтобы сменить — все вложения и итоги сессии будут сохраняться в карточке выбранного клиента.`
          : "Привязать к карточке CRM-клиента. После привязки можно прикреплять документы из звонка, и данные сессии сохранятся в карточке клиента."}
        className={
          isCall
            ? "flex h-8 shrink-0 items-center gap-1 rounded-full bg-white/15 px-2 text-xs text-white transition-opacity hover:bg-white/25 disabled:cursor-not-allowed disabled:opacity-30"
            : "flex h-[40px] shrink-0 items-center gap-1 rounded-xl px-2 text-xs transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
        }
        style={isCall ? undefined : {
          background: "var(--input-bg)",
          border: "1px solid var(--border-color)",
          color: linked ? "var(--text-primary)" : "var(--accent)",
        }}
      >
        {/* 2026-05-04 (input-bar fix): сompact mode — when linked we only
            show the icon + truncated name (max 80px), and when not linked
            we use a short label «Клиент» (was «Привязать клиента»: too wide
            for the input row, ate ~50% of the textarea width). Tooltip on
            the button still spells out the full action. */}
        {linked ? <UserIcon size={14} /> : <Link2 size={14} />}
        <span className={linked ? "max-w-[80px] truncate" : "whitespace-nowrap"}>
          {linked ? linked.full_name : "Клиент"}
        </span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Выберите CRM-клиента"
          className={
            isCall
              ? "absolute bottom-11 left-0 z-30 w-72 rounded-lg border border-white/10 bg-zinc-900/95 p-2 text-xs text-white shadow-xl backdrop-blur-md"
              : "absolute bottom-12 left-0 z-30 w-72 rounded-lg p-2 text-xs shadow-xl"
          }
          style={isCall ? undefined : {
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-color)",
            color: "var(--text-primary)",
          }}
        >
          <div
            className="mb-1.5 px-1.5 py-1 text-[10px] uppercase tracking-wide"
            style={isCall ? { color: "rgba(255,255,255,0.5)" } : { color: "var(--text-muted)" }}
          >
            {linked ? "Сменить клиента" : "CRM-клиенты"}
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 size={14} className="animate-spin" />
            </div>
          ) : clients.length === 0 ? (
            <div
              className="px-2 py-3 text-center"
              style={isCall ? { color: "rgba(255,255,255,0.6)" } : { color: "var(--text-muted)" }}
            >
              Нет CRM-клиентов. Создайте клиента в разделе CRM.
            </div>
          ) : (
            <ul className="max-h-64 overflow-y-auto">
              {clients.map((c) => {
                const isSubmitting = submitting === c.id;
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      disabled={submitting !== null}
                      onClick={() => handleSelect(c)}
                      className={
                        isCall
                          ? "flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
                          : "flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-xs disabled:cursor-not-allowed disabled:opacity-40"
                      }
                      style={isCall ? undefined : {
                        color: "var(--text-primary)",
                      }}
                      onMouseEnter={(e) => {
                        if (!isCall) {
                          (e.currentTarget as HTMLButtonElement).style.background =
                            "var(--input-bg)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!isCall) {
                          (e.currentTarget as HTMLButtonElement).style.background =
                            "transparent";
                        }
                      }}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{c.full_name}</div>
                        {c.phone && (
                          <div
                            className="truncate text-[10px]"
                            style={isCall ? { color: "rgba(255,255,255,0.5)" } : { color: "var(--text-muted)" }}
                          >
                            {c.phone}
                          </div>
                        )}
                      </div>
                      {isSubmitting && <Loader2 size={12} className="animate-spin shrink-0" />}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
