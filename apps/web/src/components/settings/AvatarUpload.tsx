"use client";

import { useState, useRef, useMemo } from "react";
import { motion } from "framer-motion";
import { Camera, Trash2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { InfoButton } from "@/components/ui/InfoButton";

const ACCEPT = "image/jpeg,image/png,image/webp,image/gif,video/mp4,video/webm";
const MAX_IMAGE_MB = 10;
const MAX_VIDEO_MB = 15;

interface AvatarUploadProps {
  currentUrl: string | null;
  userName: string;
  size?: number;
  onUploaded: (newUrl: string) => void;
  onDeleted: () => void;
}

export function AvatarUpload({ currentUrl, userName, size = 48, onUploaded, onDeleted }: AvatarUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [bust, setBust] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const avatarSrc = useMemo(() => {
    if (!currentUrl) return null;
    const sep = currentUrl.includes("?") ? "&" : "?";
    return `${currentUrl}${sep}v=${bust}`;
  }, [currentUrl, bust]);

  const handleClick = () => inputRef.current?.click();

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    const isVideo = file.type.startsWith("video/");
    const maxBytes = (isVideo ? MAX_VIDEO_MB : MAX_IMAGE_MB) * 1024 * 1024;
    if (file.size > maxBytes) {
      setError(`Макс. ${isVideo ? MAX_VIDEO_MB : MAX_IMAGE_MB}MB`);
      return;
    }

    setError(null);
    setUploading(true);
    try {
      const data = await api.upload("/users/me/avatar", file);
      setBust((n) => n + 1);
      onUploaded(data.avatar_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async () => {
    setUploading(true);
    setError(null);
    try {
      await api.delete("/users/me/avatar");
      setBust(0);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="relative inline-flex items-center gap-2">
      {/* Clickable avatar */}
      <motion.button
        type="button"
        onClick={handleClick}
        disabled={uploading}
        className="relative group"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        <UserAvatar avatarUrl={avatarSrc} fullName={userName} size={size} />
        <div
          className="absolute inset-0 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ background: "var(--overlay-bg)" }}
        >
          {uploading ? (
            <Loader2 size={size * 0.3} className="text-white animate-spin" />
          ) : (
            <Camera size={size * 0.3} className="text-white" />
          )}
        </div>
      </motion.button>

      <input ref={inputRef} type="file" accept={ACCEPT} onChange={handleFile} className="hidden" />

      <InfoButton text="JPEG, PNG, WebP, GIF, MP4, WebM · макс 10 MB" size={14} side="right" />

      {/* Delete button (only if avatar exists) */}
      {currentUrl && !uploading && (
        <motion.button
          onClick={handleDelete}
          className="ml-1"
          style={{ color: "var(--text-muted)" }}
          whileHover={{ color: "var(--danger)" }}
          whileTap={{ scale: 0.9 }}
          title="Удалить фото"
        >
          <Trash2 size={14} />
        </motion.button>
      )}

      {error && (
        <span className="text-xs ml-1" style={{ color: "var(--danger)" }}>
          {error}
        </span>
      )}
    </div>
  );
}
