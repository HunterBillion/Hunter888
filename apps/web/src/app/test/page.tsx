"use client";

import { useEffect, useState } from "react";
import Script from "next/script";
import AuthLayout from "@/components/layout/AuthLayout";

/**
 * /test — Hunter888 System Test Console
 * Loads test-suite.js with proper CSP nonce and provides a UI to run tests.
 */
export default function TestPage() {
  const [loaded, setLoaded] = useState(false);
  const [running, setRunning] = useState(false);
  const [output, setOutput] = useState<string[]>([]);

  // Capture console output
  useEffect(() => {
    const origLog = console.log;
    const origError = console.error;
    const origWarn = console.warn;
    const lines: string[] = [];

    const capture = (prefix: string) => (...args: unknown[]) => {
      const line = args.map((a) => (typeof a === "string" ? a : JSON.stringify(a))).join(" ");
      lines.push(`${prefix}${line}`);
      setOutput([...lines]);
    };

    console.log = (...args: unknown[]) => {
      origLog.apply(console, args);
      capture("")(...args);
    };
    console.error = (...args: unknown[]) => {
      origError.apply(console, args);
      capture("[ERR] ")(...args);
    };
    console.warn = (...args: unknown[]) => {
      origWarn.apply(console, args);
      capture("[WARN] ")(...args);
    };

    return () => {
      console.log = origLog;
      console.error = origError;
      console.warn = origWarn;
    };
  }, []);

  const runTests = async (group?: string) => {
    setRunning(true);
    setOutput([]);
    try {
      const H = (window as any).Hunter888Test;
      if (!H) {
        setOutput(["ERROR: Hunter888Test not loaded. Reload the page."]);
        return;
      }
      if (group) {
        await H[group]();
      } else {
        await H.runAll();
      }
    } catch (e: any) {
      setOutput((prev) => [...prev, `FATAL: ${e.message}`]);
    } finally {
      setRunning(false);
    }
  };

  const groups = [
    { key: "auth", label: "Auth", icon: "🔐" },
    { key: "gamification", label: "Gamification", icon: "🎮" },
    { key: "training", label: "Training", icon: "🎯" },
    { key: "pvp", label: "PvP", icon: "⚔️" },
    { key: "crm", label: "CRM", icon: "👥" },
    { key: "security", label: "Security", icon: "🛡️" },
    { key: "integrity", label: "Integrity", icon: "🔍" },
    { key: "stress", label: "Stress", icon: "💪" },
    { key: "websocket", label: "WebSocket", icon: "🔌" },
  ];

  return (
    <AuthLayout>
    <div className="min-h-screen bg-black text-green-400 font-mono p-6">
      <Script
        src="/test-suite.js"
        strategy="afterInteractive"
        onLoad={() => setLoaded(true)}
      />

      <h1 className="text-2xl mb-4 text-green-300">
        🔥 Hunter888 System Test Suite
      </h1>

      {!loaded && (
        <div className="text-yellow-400 mb-4 animate-pulse">
          Loading test-suite.js...
        </div>
      )}

      {loaded && (
        <div className="flex flex-wrap gap-2 mb-6">
          <button
            onClick={() => runTests()}
            disabled={running}
            className="px-4 py-2 bg-green-900 hover:bg-green-800 text-green-200 rounded border border-green-700 disabled:opacity-40 font-bold"
          >
            {running ? "⏳ Running..." : "▶ RUN ALL (55+ tests)"}
          </button>

          <div className="w-full" />

          {groups.map((g) => (
            <button
              key={g.key}
              onClick={() => runTests(g.key)}
              disabled={running}
              className="px-3 py-1.5 bg-gray-900 hover:bg-gray-800 text-gray-300 rounded border border-gray-700 disabled:opacity-40 text-sm"
            >
              {g.icon} {g.label}
            </button>
          ))}

          <button
            onClick={async () => {
              const H = (window as any).Hunter888Test;
              if (H) await H.responseSizes();
            }}
            disabled={running}
            className="px-3 py-1.5 bg-gray-900 hover:bg-gray-800 text-gray-300 rounded border border-gray-700 disabled:opacity-40 text-sm"
          >
            📊 Response Sizes
          </button>
        </div>
      )}

      {/* Output terminal */}
      <div className="bg-gray-950 border border-gray-800 rounded-lg p-4 max-h-[70vh] overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed">
        {output.length === 0 && (
          <span className="text-gray-600">
            {loaded
              ? "Press RUN ALL to start testing...\n\nYou can also open DevTools Console (F12) and run:\n  await Hunter888Test.runAll()"
              : "Loading..."}
          </span>
        )}
        {output.map((line, i) => (
          <div
            key={i}
            className={
              line.includes("✅")
                ? "text-green-400"
                : line.includes("❌")
                  ? "text-red-400"
                  : line.includes("═") || line.includes("📋")
                    ? "text-cyan-400 font-bold"
                    : line.includes("📊") || line.includes("🔥")
                      ? "text-yellow-300 font-bold"
                      : line.includes("[ERR]")
                        ? "text-red-500"
                        : "text-gray-400"
            }
          >
            {line}
          </div>
        ))}
      </div>
    </div>
    </AuthLayout>
  );
}
