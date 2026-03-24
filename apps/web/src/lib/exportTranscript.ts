/**
 * Export training session transcript as a downloadable text/markdown file.
 */

interface TranscriptMessage {
  role: "user" | "assistant" | "system";
  text: string;
  timestamp?: string;
}

interface TranscriptMeta {
  sessionId: string;
  scenarioTitle?: string;
  date: string;
  score?: number | null;
  emotion?: string;
  duration?: string;
}

/**
 * Formats transcript messages into a readable Markdown string.
 */
function formatTranscript(meta: TranscriptMeta, messages: TranscriptMessage[]): string {
  const lines: string[] = [];

  lines.push(`# Транскрипт тренировки`);
  lines.push("");
  lines.push(`- **Сессия:** ${meta.sessionId}`);
  if (meta.scenarioTitle) lines.push(`- **Сценарий:** ${meta.scenarioTitle}`);
  lines.push(`- **Дата:** ${meta.date}`);
  if (meta.duration) lines.push(`- **Длительность:** ${meta.duration}`);
  if (meta.score !== null && meta.score !== undefined) lines.push(`- **Итоговый балл:** ${Math.round(meta.score)}/100`);
  if (meta.emotion) lines.push(`- **Финальная эмоция:** ${meta.emotion}`);
  lines.push("");
  lines.push("---");
  lines.push("");

  for (const msg of messages) {
    const speaker = msg.role === "user" ? "🎤 **Менеджер**" : msg.role === "assistant" ? "🤖 **Клиент (AI)**" : "📋 **Система**";
    const time = msg.timestamp ? ` _[${msg.timestamp}]_` : "";
    lines.push(`${speaker}${time}`);
    lines.push("");
    lines.push(msg.text);
    lines.push("");
  }

  lines.push("---");
  lines.push(`_Экспортировано из VibeHunter ${new Date().toLocaleDateString("ru-RU")}_`);

  return lines.join("\n");
}

/**
 * Triggers a file download of the transcript.
 */
export function downloadTranscript(meta: TranscriptMeta, messages: TranscriptMessage[]) {
  const content = formatTranscript(meta, messages);
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = `transcript-${meta.sessionId.slice(0, 8)}-${meta.date.replace(/[\/\s:]/g, "-")}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Copies transcript to clipboard.
 */
export async function copyTranscript(meta: TranscriptMeta, messages: TranscriptMessage[]): Promise<boolean> {
  const content = formatTranscript(meta, messages);
  try {
    await navigator.clipboard.writeText(content);
    return true;
  } catch {
    return false;
  }
}
