"use client";

import { motion } from "framer-motion";

interface SkeletonProps {
  className?: string;
  width?: string | number;
  height?: string | number;
  rounded?: string;
}

export function Skeleton({ className = "", width, height, rounded = "8px" }: SkeletonProps) {
  return (
    <motion.div
      className={`relative overflow-hidden ${className}`}
      style={{
        width,
        height,
        borderRadius: rounded,
        background: "var(--input-bg)",
      }}
      animate={{ opacity: [0.4, 0.7, 0.4] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
    >
      <motion.div
        className="absolute inset-0"
        style={{
          background: "linear-gradient(90deg, transparent 0%, var(--accent-muted) 50%, transparent 100%)",
        }}
        animate={{ x: ["-100%", "100%"] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
      />
    </motion.div>
  );
}

// Pre-built skeleton layouts
export function CardSkeleton() {
  return (
    <div className="glass-panel p-5 space-y-3">
      <Skeleton height={14} width="40%" />
      <Skeleton height={28} width="60%" />
      <Skeleton height={10} width="80%" />
    </div>
  );
}

export function ListItemSkeleton() {
  return (
    <div className="glass-panel p-5 flex items-center gap-4">
      <Skeleton width={40} height={40} rounded="12px" />
      <div className="flex-1 space-y-2">
        <Skeleton height={12} width="50%" />
        <Skeleton height={10} width="70%" />
      </div>
      <Skeleton width={40} height={24} rounded="4px" />
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8 space-y-6">
      <div className="space-y-2">
        <Skeleton height={28} width="30%" />
        <Skeleton height={12} width="50%" />
      </div>
      <Skeleton height={12} width="100%" rounded="999px" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => <CardSkeleton key={i} />)}
      </div>
      <div className="space-y-3">
        {[1, 2, 3].map(i => <ListItemSkeleton key={i} />)}
      </div>
    </div>
  );
}
