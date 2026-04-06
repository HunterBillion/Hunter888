"use client";

import { motion } from "framer-motion";
import { Phone, PhoneIncoming, Mail, MessageSquare, Users, FileText, ArrowRightLeft, Shield, Settings } from "lucide-react";
import type { ClientInteraction, InteractionType } from "@/types";

const ICON_MAP: Record<InteractionType, typeof Phone> = {
  outbound_call: Phone,
  inbound_call: PhoneIncoming,
  sms_sent: MessageSquare,
  whatsapp_sent: MessageSquare,
  email_sent: Mail,
  meeting: Users,
  status_change: ArrowRightLeft,
  consent_event: Shield,
  note: FileText,
  system: Settings,
};

const TYPE_LABELS: Record<InteractionType, string> = {
  outbound_call: "Исходящий",
  inbound_call: "Входящий",
  sms_sent: "SMS",
  whatsapp_sent: "WhatsApp",
  email_sent: "Email",
  meeting: "Встреча",
  status_change: "Смена статуса",
  consent_event: "Согласие",
  note: "Заметка",
  system: "Система",
};

interface ClientTimelineProps {
  interactions: ClientInteraction[];
}

export function ClientTimeline({ interactions }: ClientTimelineProps) {
  if (!interactions.length) {
    return (
      <div className="text-center py-8">
        <span className="text-sm" style={{ color: "var(--text-muted)" }}>Нет взаимодействий</span>
      </div>
    );
  }

  return (
    <div className="relative pl-6">
      {/* Vertical line */}
      <div
        className="absolute left-[9px] top-2 bottom-2 w-px"
        style={{ background: "var(--border-color)" }}
      />

      {interactions.map((item, i) => {
        const Icon = ICON_MAP[item.interaction_type] || FileText;
        const dateStr = new Date(item.created_at).toLocaleDateString("ru-RU", {
          day: "numeric",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        });

        return (
          <motion.div
            key={item.id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="relative pb-5 last:pb-0"
          >
            {/* Dot */}
            <div
              className="absolute -left-6 top-1 w-[18px] h-[18px] rounded-full flex items-center justify-center"
              style={{ background: "var(--bg-secondary)", border: "2px solid var(--accent)" }}
            >
              <Icon size={9} style={{ color: "var(--accent)" }} />
            </div>

            {/* Content */}
            <div className="ml-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono" style={{ color: "var(--accent)" }}>
                  {TYPE_LABELS[item.interaction_type]}
                </span>
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {dateStr}
                </span>
              </div>
              <p className="text-sm mt-0.5" style={{ color: "var(--text-primary)" }}>
                {item.content}
              </p>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                {item.manager_name}
              </span>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
