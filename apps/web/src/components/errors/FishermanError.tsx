"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { RotateCcw } from "lucide-react";
import { useReducedMotion } from "@/hooks/useReducedMotion";

// ── Error fish that swim across ────────────────────────────
const ERROR_FISH = [
  { code: "404", label: "Not Found" },
  { code: "500", label: "Server Error" },
  { code: "503", label: "Unavailable" },
  { code: "408", label: "Timeout" },
  { code: "ERR", label: "No Connection" },
  { code: "DNS", label: "DNS Failed" },
];

interface Fish {
  id: number;
  code: string;
  label: string;
  x: number;
  y: number;
  speed: number;
  size: number;
  caught: boolean;
  isGolden: boolean;
  direction: 1 | -1; // 1 = right-to-left, -1 = left-to-right
}

interface FallingStar {
  id: number;
  x: number;
  startTime: number;
}

interface FishermanErrorProps {
  onRetry: () => void;
  message?: string;
}

export function FishermanError({ onRetry, message }: FishermanErrorProps) {
  const [fish, setFish] = useState<Fish[]>([]);
  const [hookDrop, setHookDrop] = useState(0); // 0..1 progress
  const [casting, setCasting] = useState(false);
  const [score, setScore] = useState(0);
  const [caught, setCaught] = useState<string | null>(null);
  const [goldenCaught, setGoldenCaught] = useState(false);
  const [fallingStars, setFallingStars] = useState<FallingStar[]>([]);
  const fishIdRef = useRef(0);
  const starIdRef = useRef(0);
  const animRef = useRef(0);
  const timeRef = useRef(Date.now());
  const reducedMotion = useReducedMotion();

  // Stable star positions
  const stars = useMemo(() =>
    Array.from({ length: 30 }, (_, i) => ({
      id: i,
      size: 1 + (i * 7 % 3),
      x: (i * 37 + 13) % 100,
      y: (i * 23 + 7) % 40,
      dur: 2 + (i % 4),
      delay: (i * 0.3) % 3,
    })),
  []);

  // Spawn fish periodically
  useEffect(() => {
    const interval = setInterval(() => {
      setFish((prev) => {
        if (prev.length > 8) return prev;
        const isGolden = Math.random() < 0.08;
        const template = ERROR_FISH[Math.floor(Math.random() * ERROR_FISH.length)];
        fishIdRef.current += 1;
        // Fish swim from right to left (direction = 1) or left to right
        const fromRight = Math.random() > 0.3; // 70% from right
        return [
          ...prev,
          {
            id: fishIdRef.current,
            code: isGolden ? "✦" : template.code,
            label: isGolden ? "Соединение!" : template.label,
            x: fromRight ? 110 : -10,
            y: 60 + Math.random() * 25,
            speed: 0.4 + Math.random() * 0.4,
            size: isGolden ? 1.8 : 1.0 + Math.random() * 0.6,
            caught: false,
            isGolden,
            direction: fromRight ? 1 : -1,
          },
        ];
      });
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  // Animate fish movement (skip rAF loop for reduced motion — use slower interval)
  useEffect(() => {
    if (reducedMotion) {
      // Simplified: move fish via interval instead of rAF
      const id = setInterval(() => {
        setFish((prev) =>
          prev
            .map((f) => ({
              ...f,
              x: f.caught ? f.x : f.x + (f.direction === 1 ? -f.speed * 4 : f.speed * 4),
              y: f.caught ? f.y - 3 : f.y,
            }))
            .filter((f) => {
              if (f.caught) return f.y > 10;
              if (f.direction === 1) return f.x > -15;
              return f.x < 115;
            }),
        );
      }, 200);
      return () => clearInterval(id);
    }
    const tick = () => {
      const now = Date.now();
      setFish((prev) =>
        prev
          .map((f) => ({
            ...f,
            x: f.caught ? f.x : f.x + (f.direction === 1 ? -f.speed : f.speed),
            y: f.caught ? f.y - 1.5 : f.y + Math.sin(now * 0.003 + f.id * 2) * 0.2,
          }))
          .filter((f) => {
            if (f.caught) return f.y > 10;
            // Remove fish that have swum off screen
            if (f.direction === 1) return f.x > -15;
            return f.x < 115;
          }),
      );
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [reducedMotion]);

  // Spawn falling star on catch
  const spawnFallingStar = useCallback(() => {
    starIdRef.current += 1;
    const star: FallingStar = {
      id: starIdRef.current,
      x: 15 + Math.random() * 70,
      startTime: Date.now(),
    };
    setFallingStars((prev) => [...prev, star]);
    setTimeout(() => {
      setFallingStars((prev) => prev.filter((s) => s.id !== star.id));
    }, 1500);
  }, []);

  // Cast hook — hook drops down into the water
  const castHook = useCallback(() => {
    if (casting) return;
    setCasting(true);
    setCaught(null);

    let frame = 0;
    const maxFrames = 80;
    const animate = () => {
      frame++;
      const progress = frame / maxFrames;
      // Hook goes down smoothly, pauses at bottom, comes back up
      const drop = progress < 0.5
        ? Math.sin(progress * Math.PI) // down
        : Math.sin(progress * Math.PI); // up (same curve, symmetric)
      setHookDrop(drop);

      // Check collision near the deepest point
      if (frame === Math.floor(maxFrames * 0.5)) {
        setFish((prev) => {
          const hookX = 58; // rod tip X position (% of screen)
          const hookDepth = 58 + drop * 24; // water surface ~58%, max depth ~82%
          let caughtFish: Fish | null = null;

          const updated = prev.map((f) => {
            if (f.caught) return f;
            const dx = Math.abs(f.x - hookX);
            const dy = Math.abs(f.y - hookDepth);
            if (dx < 10 && dy < 8 && !caughtFish) {
              caughtFish = f;
              return { ...f, caught: true };
            }
            return f;
          });

          if (caughtFish) {
            const cf = caughtFish as Fish;
            setScore((s) => s + (cf.isGolden ? 100 : 10));
            setCaught(cf.isGolden ? "golden" : cf.code);
            spawnFallingStar();
            if (cf.isGolden) {
              setGoldenCaught(true);
              setTimeout(onRetry, 2000);
            }
          }

          return updated;
        });
      }

      if (frame < maxFrames) {
        requestAnimationFrame(animate);
      } else {
        setHookDrop(0);
        setCasting(false);
      }
    };
    requestAnimationFrame(animate);
  }, [casting, onRetry, spawnFallingStar]);

  // Keyboard handler
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        e.preventDefault();
        castHook();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [castHook]);

  // Hook absolute position for the fishing line
  const hookLineLength = hookDrop * 120; // pixels the hook drops

  return (
    <div
      className="fixed inset-0 z-[200] flex flex-col items-center justify-center overflow-hidden"
      style={{
        background: "linear-gradient(180deg, var(--bg-primary) 0%, var(--bg-secondary) 40%, var(--bg-tertiary) 100%)",
      }}
      onClick={castHook}
    >
      {/* Stars */}
      {stars.map((s) => (
        <motion.div
          key={s.id}
          className="absolute rounded-full"
          style={{
            width: s.size,
            height: s.size,
            background: "var(--text-muted)",
            opacity: 0.4,
            left: `${s.x}%`,
            top: `${s.y}%`,
          }}
          animate={reducedMotion ? {} : { opacity: [0.2, 0.6, 0.2] }}
          transition={reducedMotion ? {} : { duration: s.dur, repeat: Infinity, delay: s.delay }}
        />
      ))}

      {/* Falling stars on catch */}
      <AnimatePresence>
        {fallingStars.map((fs) => (
          <motion.div
            key={fs.id}
            className="absolute pointer-events-none"
            style={{ left: `${fs.x}%`, top: 0 }}
            initial={{ y: -20, opacity: 1 }}
            animate={{ y: "60vh", opacity: [1, 1, 0] }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.2, ease: "easeIn" }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <polygon
                points="8,0 10,6 16,6 11,10 13,16 8,12 3,16 5,10 0,6 6,6"
                fill="#FFD700"
              />
            </svg>
            {/* Trail */}
            <motion.div
              className="absolute top-0 left-1/2 -translate-x-1/2 w-[2px]"
              style={{ background: "linear-gradient(180deg, #FFD700, transparent)", height: 40 }}
              initial={{ opacity: 0.8, scaleY: 0 }}
              animate={{ opacity: [0.8, 0], scaleY: 1 }}
              transition={{ duration: 0.8 }}
            />
          </motion.div>
        ))}
      </AnimatePresence>

      {/* Moon */}
      <div
        className="absolute rounded-full"
        style={{
          width: 50,
          height: 50,
          background: "radial-gradient(circle, rgba(255,230,180,0.9) 0%, rgba(255,200,100,0.3) 60%, transparent 80%)",
          top: "8%",
          right: "15%",
          boxShadow: "0 0 40px rgba(255,200,100,0.3)",
        }}
      />

      {/* Animated water surface — SVG wave */}
      <div className="absolute left-0 right-0" style={{ top: "55%" }}>
        <svg
          width="100%"
          height="20"
          viewBox="0 0 1200 20"
          preserveAspectRatio="none"
          className="block"
        >
          <motion.path
            d="M0,10 Q100,4 200,10 T400,10 T600,10 T800,10 T1000,10 T1200,10"
            fill="none"
            stroke="rgba(138,43,226,0.4)"
            strokeWidth="2"
            animate={{
              d: [
                "M0,10 Q100,4 200,10 T400,10 T600,10 T800,10 T1000,10 T1200,10",
                "M0,10 Q100,16 200,10 T400,10 T600,10 T800,10 T1000,10 T1200,10",
                "M0,10 Q100,4 200,10 T400,10 T600,10 T800,10 T1000,10 T1200,10",
              ],
            }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          />
          <motion.path
            d="M0,12 Q150,6 300,12 T600,12 T900,12 T1200,12"
            fill="none"
            stroke="rgba(138,43,226,0.2)"
            strokeWidth="1.5"
            animate={{
              d: [
                "M0,12 Q150,6 300,12 T600,12 T900,12 T1200,12",
                "M0,12 Q150,18 300,12 T600,12 T900,12 T1200,12",
                "M0,12 Q150,6 300,12 T600,12 T900,12 T1200,12",
              ],
            }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
          />
        </svg>
      </div>

      {/* Water below surface */}
      <div
        className="absolute left-0 right-0 bottom-0"
        style={{
          top: "56%",
          background: "linear-gradient(180deg, rgba(20,10,50,0.5) 0%, rgba(10,5,30,0.8) 100%)",
        }}
      />

      {/* Boat + fisherman — sits on the water surface */}
      <motion.div
        className="absolute"
        style={{ top: "50%", left: "calc(50% - 50px)" }}
        animate={reducedMotion ? {} : {
          y: [0, -4, 0, 3, 0],
          rotate: [-1, 1.5, -0.5, 1, -1],
        }}
        transition={reducedMotion ? {} : { duration: 3.5, repeat: Infinity, ease: "easeInOut" }}
      >
        {/* Water splash around boat */}
        <motion.div
          className="absolute"
          style={{ bottom: -4, left: -8, right: -8, height: 8 }}
          animate={{ opacity: [0.2, 0.4, 0.2] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          <svg width="116" height="8" viewBox="0 0 116 8" preserveAspectRatio="none">
            <motion.path
              d="M0,4 Q15,1 30,4 T60,4 T90,4 T116,4"
              fill="none"
              stroke="rgba(138,43,226,0.3)"
              strokeWidth="1"
              animate={{
                d: [
                  "M0,4 Q15,1 30,4 T60,4 T90,4 T116,4",
                  "M0,4 Q15,7 30,4 T60,4 T90,4 T116,4",
                  "M0,4 Q15,1 30,4 T60,4 T90,4 T116,4",
                ],
              }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            />
          </svg>
        </motion.div>

        {/* Boat body */}
        <svg width="100" height="40" viewBox="0 0 100 40">
          <path
            d="M10,15 Q15,5 30,8 L70,8 Q85,5 90,15 Q85,30 70,28 L30,28 Q15,30 10,15Z"
            fill="#5c3a1e"
            stroke="#3d2510"
            strokeWidth="1.5"
          />
          <line x1="25" y1="10" x2="25" y2="26" stroke="#4a2e15" strokeWidth="0.5" />
          <line x1="50" y1="8" x2="50" y2="28" stroke="#4a2e15" strokeWidth="0.5" />
          <line x1="75" y1="10" x2="75" y2="26" stroke="#4a2e15" strokeWidth="0.5" />
        </svg>

        {/* Fisherman */}
        <div className="absolute" style={{ top: -32, left: 30 }}>
          {/* Hat */}
          <div
            style={{
              width: 36,
              height: 12,
              borderRadius: "50%",
              background: "#c4a050",
              position: "relative",
            }}
          >
            <div
              style={{
                width: 20,
                height: 14,
                borderRadius: "50% 50% 0 0",
                background: "#b89040",
                position: "absolute",
                left: 8,
                top: -10,
              }}
            />
          </div>
          {/* Body */}
          <div
            style={{
              width: 20,
              height: 18,
              background: "#4a6080",
              borderRadius: "4px 4px 0 0",
              marginLeft: 8,
              marginTop: 2,
            }}
          />
        </div>

        {/* Fishing rod — swings on cast */}
        <motion.div
          className="absolute"
          style={{ top: -38, left: 55, transformOrigin: "bottom left" }}
          animate={{ rotate: casting ? [0, -25, 10, 0] : [0, -1.5, 0, 1, 0] }}
          transition={casting ? { duration: 0.6 } : { duration: 3, repeat: Infinity }}
        >
          {/* Rod stick */}
          <svg width="90" height="60" viewBox="0 0 90 60" overflow="visible">
            <line x1="0" y1="55" x2="80" y2="0" stroke="#8b7355" strokeWidth="2.5" strokeLinecap="round" />
            <line x1="0" y1="55" x2="80" y2="0" stroke="#a08060" strokeWidth="1" strokeLinecap="round" />
            {/* Fishing line drops from rod tip */}
            <line
              x1="80" y1="0"
              x2="80" y2={hookLineLength}
              stroke="rgba(200,200,200,0.5)"
              strokeWidth="0.8"
              strokeDasharray="4,2"
            />
            {/* Hook/float at the end of the line */}
            <g transform={`translate(75, ${hookLineLength - 2})`}>
              <circle r="5" fill="rgba(138,43,226,0.6)" stroke="rgba(200,150,255,0.5)" strokeWidth="1" />
              <WifiIcon x={-3.5} y={-3.5} />
            </g>
          </svg>
        </motion.div>
      </motion.div>

      {/* Swimming error fish — face the direction they swim */}
      {fish.map((f) => (
        <motion.div
          key={f.id}
          className="absolute pointer-events-none"
          style={{
            left: `${f.x}%`,
            top: `${f.y}%`,
            opacity: f.caught ? 0.3 : 1,
          }}
          animate={f.caught ? { y: -50, opacity: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <div
            className="flex items-center gap-1"
            style={{
              transform: `scale(${f.size}) scaleX(${f.direction === 1 ? 1 : -1})`,
            }}
          >
            {/* Fish body — always faces left (mouth left, tail right) */}
            <svg width="44" height="22" viewBox="-2 -1 48 22" style={{ filter: f.isGolden ? "drop-shadow(0 0 6px #FFD700)" : "drop-shadow(0 0 4px rgba(138,43,226,0.5))" }}>
              {/* Tail */}
              <polygon
                points="36,10 46,3 46,17"
                fill={f.isGolden ? "#FFD700" : "rgba(140,80,220,0.7)"}
              />
              {/* Body */}
              <ellipse
                cx="20" cy="10" rx="16" ry="8"
                fill={f.isGolden ? "#FFD700" : "rgba(140,80,220,0.8)"}
                stroke={f.isGolden ? "#FFA500" : "rgba(180,120,255,0.6)"}
                strokeWidth="1.5"
              />
              {/* Eye */}
              <circle cx="10" cy="8" r="2.5" fill={f.isGolden ? "#333" : "rgba(255,255,255,0.9)"} />
              <circle cx="9.5" cy="7.5" r="1" fill={f.isGolden ? "#111" : "rgba(60,20,120,0.9)"} />
              {/* Fin */}
              <path
                d="M18,16 Q22,22 26,16"
                fill={f.isGolden ? "#FFC000" : "rgba(120,60,200,0.5)"}
              />
            </svg>
          </div>
          {/* Code label — always readable (not mirrored) */}
          <span
            className="absolute -top-4 left-1/2 -translate-x-1/2 font-mono text-[10px] font-bold whitespace-nowrap"
            style={{
              color: f.isGolden ? "#FFD700" : "rgba(200,170,255,0.9)",
              textShadow: f.isGolden ? "0 0 8px #FFD700" : "0 0 6px rgba(138,43,226,0.5)",
            }}
          >
            {f.code}
          </span>
        </motion.div>
      ))}

      {/* Catch notification */}
      <AnimatePresence>
        {caught && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.8 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20 }}
            className="absolute font-mono text-sm font-bold px-4 py-2 rounded-xl"
            style={{
              top: "38%",
              background: caught === "golden" ? "rgba(255,215,0,0.2)" : "rgba(138,43,226,0.2)",
              border: `1px solid ${caught === "golden" ? "rgba(255,215,0,0.4)" : "rgba(138,43,226,0.3)"}`,
              color: caught === "golden" ? "#FFD700" : "rgba(200,180,255,0.8)",
              boxShadow: caught === "golden" ? "0 0 20px rgba(255,215,0,0.3)" : "none",
            }}
          >
            {caught === "golden" ? "🐟 Золотая рыбка! Соединение восстанавливается..." : `Поймана: ${caught}`}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Golden catch celebration */}
      <AnimatePresence>
        {goldenCaught && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="absolute inset-0 pointer-events-none"
            style={{
              background: "radial-gradient(circle at 50% 50%, rgba(255,215,0,0.15), transparent 60%)",
            }}
          />
        )}
      </AnimatePresence>

      {/* Error message plaque */}
      <div
        className="absolute text-center"
        style={{ bottom: "8%", left: "50%", transform: "translateX(-50%)" }}
      >
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
        >
          <p className="font-mono text-sm mb-1" style={{ color: "rgba(200,180,230,0.7)" }}>
            {message || "Похоже, рыба сегодня не клюёт..."}
          </p>
          <p className="font-mono text-[10px] mb-4" style={{ color: "rgba(160,140,200,0.5)" }}>
            как и твой интернет
          </p>

          <div className="flex items-center justify-center gap-3">
            <motion.button
              onClick={(e) => { e.stopPropagation(); onRetry(); }}
              className="flex items-center gap-2 rounded-xl px-5 py-2.5 font-mono text-xs tracking-wider"
              style={{
                background: "rgba(138,43,226,0.15)",
                border: "1px solid rgba(138,43,226,0.3)",
                color: "rgba(200,180,255,0.8)",
              }}
              whileHover={{ background: "rgba(138,43,226,0.25)", borderColor: "rgba(138,43,226,0.5)" }}
              whileTap={{ scale: 0.95 }}
            >
              <RotateCcw size={14} />
              Закинуть удочку ещё раз
            </motion.button>
          </div>

          <p className="mt-4 font-mono text-[9px]" style={{ color: "rgba(140,120,180,0.4)" }}>
            Пробел / Клик — забросить крючок &nbsp;|&nbsp; Счёт: {score}
          </p>
        </motion.div>
      </div>
    </div>
  );
}

// Mini Wi-Fi icon for SVG
function WifiIcon({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <line x1="3.5" y1="7" x2="3.5" y2="7" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M1.5,5 Q3.5,3 5.5,5" stroke="white" strokeWidth="0.8" fill="none" />
      <path d="M0,3 Q3.5,0 7,3" stroke="white" strokeWidth="0.8" fill="none" />
    </g>
  );
}
