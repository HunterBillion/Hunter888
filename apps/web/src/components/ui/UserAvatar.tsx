"use client";

import { useEffect, useState } from "react";
import { getApiBaseUrl } from "@/lib/public-origin";

interface UserAvatarProps {
  avatarUrl?: string | null;
  fullName: string;
  size?: number;
  className?: string;
}

function resolveUrl(url: string): string {
  if (url.startsWith("http")) return url;
  return `${getApiBaseUrl()}${url}`;
}

function isVideo(url: string): boolean {
  return /\.(mp4|webm)(\?|$)/i.test(url);
}

export function UserAvatar({ avatarUrl, fullName, size = 32, className = "" }: UserAvatarProps) {
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [avatarUrl]);

  const initials = fullName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  const sizeStyle = { width: size, height: size, minWidth: size, minHeight: size };
  const fontSize = Math.max(10, size * 0.38);

  if (avatarUrl && !imageFailed) {
    const src = resolveUrl(avatarUrl);

    if (isVideo(avatarUrl)) {
      return (
        <div
          className={`rounded-full overflow-hidden shrink-0 ${className}`}
          style={sizeStyle}
        >
          <video
            src={src}
            autoPlay
            muted
            loop
            playsInline
            className="w-full h-full object-cover"
          />
        </div>
      );
    }

    return (
      <div
        className={`rounded-full overflow-hidden shrink-0 ${className}`}
        style={sizeStyle}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={fullName}
          className="w-full h-full object-cover"
          onError={() => setImageFailed(true)}
        />
      </div>
    );
  }

  // Fallback: initials (or after image load error)
  return (
    <div
      className={`rounded-full flex items-center justify-center shrink-0 font-mono font-semibold text-white ${className}`}
      style={{
        ...sizeStyle,
        background: "var(--accent)",
        fontSize,
      }}
    >
      {initials}
    </div>
  );
}
