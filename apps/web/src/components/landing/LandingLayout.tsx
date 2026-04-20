"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  Mail,
  AlertCircle,
  User,
  X as XIcon,
} from "lucide-react";
import { FishermanError } from "@/components/errors/FishermanError";
import { Button } from "@/components/ui/Button";
import { getToken, setTokens } from "@/lib/auth";
import { api } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/public-origin";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { PasswordChecklist, isPasswordValid } from "@/components/ui/PasswordChecklist";
import { XHunterLogo } from "@/components/ui/XHunterLogo";
import { LandingNavbar } from "./LandingNavbar";
import { LandingFooter } from "./LandingFooter";
import { LandingAuthContext, type Panel } from "./LandingAuthContext";

type ForgotMode = "idle" | "form" | "sent";

const SSO_BUTTONS = [
  {
    label: "Google",
    endpoint: "/auth/google/login",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24">
        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
      </svg>
    ),
  },
  {
    label: "Yandex",
    endpoint: "/auth/yandex/login",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24">
        <path d="M2 12C2 6.48 6.48 2 12 2s10 4.48 10 10-4.48 10-10 10S2 17.52 2 12z" fill="#FC3F1D" />
        <path d="M13.32 17.5h-1.88V7.38h-.97c-1.57 0-2.39.8-2.39 1.95 0 1.3.59 1.9 1.8 2.7l1 .65-2.9 4.82H6l2.62-4.33C7.37 12.26 6.56 11.22 6.56 9.5c0-2.07 1.45-3.5 4-3.5h2.76V17.5z" fill="white" />
      </svg>
    ),
  },
];

export function LandingLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [activePanel, setActivePanel] = useState<Panel>(null);
  const [networkError, setNetworkError] = useState(false);

  // Main form
  const [email, setEmail] = useState(() => {
    if (typeof window !== "undefined") return sessionStorage.getItem("vh-auth-email") ?? "";
    return "";
  });
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState(() => {
    if (typeof window !== "undefined") return sessionStorage.getItem("vh-auth-name") ?? "";
    return "";
  });
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Forgot password
  const [forgotMode, setForgotMode] = useState<ForgotMode>("idle");
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotLoading, setForgotLoading] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) { setCheckingAuth(false); return; }
    api.get("/consent/status")
      .then((d) => router.replace(d.all_accepted ? "/home" : "/consent"))
      .catch(() => router.replace("/home"));
  }, [router]);

  const openPanel = (panel: Panel) => {
    setActivePanel(panel);
    setError("");
    setEmail(""); setPassword(""); setConfirmPassword(""); setFullName("");
    setForgotMode("idle"); setForgotEmail("");
  };
  const closePanel = () => { setActivePanel(null); setError(""); setForgotMode("idle"); };

  // Escape key closes drawer
  useEffect(() => {
    if (!activePanel) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") closePanel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activePanel]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (activePanel === "register") {
      if (!fullName.trim()) { setError("Укажите имя"); return; }
      if (!isPasswordValid(password)) { setError("Пароль не соответствует требованиям"); return; }
      if (password !== confirmPassword) { setError("Пароли не совпадают"); return; }
    }
    setLoading(true);
    try {
      if (activePanel === "login") {
        const data = await api.post("/auth/login", { email: email.trim(), password });
        setTokens(data.access_token, data.refresh_token, data.csrf_token);
        try { sessionStorage.removeItem("vh-auth-email"); sessionStorage.removeItem("vh-auth-name"); } catch {}
        router.push(data.must_change_password ? "/change-password" : "/home");
      } else {
        const data = await api.post("/auth/register", {
          email: email.trim(), password, full_name: fullName.trim(),
        });
        setTokens(data.access_token, data.refresh_token, data.csrf_token);
        router.push("/onboarding");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка";
      if (msg.includes("недоступен") || msg.includes("fetch") || msg.includes("network")) {
        setNetworkError(true);
      } else { setError(msg); }
    } finally { setLoading(false); }
  };

  const handleForgot = async () => {
    if (!forgotEmail.trim()) return;
    setForgotLoading(true);
    try {
      await fetch(`${getApiBaseUrl()}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: forgotEmail.trim() }),
      });
    } catch { /* silent — always show success for security */ }
    setForgotLoading(false);
    setForgotMode("sent");
  };

  const handleSso = async (endpoint: string, label: string) => {
    if (loading) return; // debounce: prevent double-click
    setLoading(true);
    try {
      const data = await api.get(endpoint);
      if (data?.url) {
        const { validateOAuthUrl } = await import("@/lib/sanitize");
        const safeUrl = validateOAuthUrl(data.url);
        if (safeUrl) {
          window.location.href = safeUrl;
        } else {
          setError(`Недоверенный OAuth URL от ${label}`);
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `${label} OAuth недоступен`);
    } finally { setLoading(false); }
  };

  const contextValue = useMemo(() => ({
    openLogin: () => openPanel("login"),
    openRegister: () => openPanel("register"),
  }), []); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Early returns ── */
  if (networkError) {
    return (
      <FishermanError
        onRetry={() => { setNetworkError(false); setError(""); }}
        message="Похоже, рыба сегодня не клюёт..."
      />
    );
  }
  if (checkingAuth) {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full animate-ping" style={{ background: "var(--accent)" }} />
          <span className="font-mono text-sm tracking-wider" style={{ color: "var(--text-muted)" }}>ИНИЦИАЛИЗАЦИЯ...</span>
        </motion.div>
      </div>
    );
  }

  const passwordsMatch = confirmPassword.length === 0 || password === confirmPassword;

  return (
    <LandingAuthContext.Provider value={contextValue}>
      <div style={{ background: "var(--bg-primary)" }}>
        <LandingNavbar
          onLogin={() => openPanel("login")}
          onRegister={() => openPanel("register")}
        />

        {children}

        <LandingFooter />

        {/* ═══ AUTH DRAWER ══════════════════════════════════════════════ */}
        <AnimatePresence>
          {activePanel && (
            <>
              {/* Backdrop */}
              <motion.div
                key="backdrop"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="fixed inset-0 z-[200] cursor-pointer"
                style={{ background: "rgba(0,0,0,0.85)", backdropFilter: "blur(8px)" }}
                onClick={closePanel}
              />

              {/* Drawer */}
              <motion.div
                key="drawer"
                role="dialog"
                aria-modal="true"
                aria-label={activePanel === "login" ? "Вход в систему" : "Регистрация"}
                initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
                transition={{ type: "spring", stiffness: 320, damping: 32 }}
                className="fixed right-0 top-0 bottom-0 z-[201] w-full sm:max-w-[440px] overflow-y-auto"
                style={{
                  background: "var(--bg-primary)",
                  borderLeft: "1px solid var(--border-color)",
                  boxShadow: "-24px 0 80px rgba(0,0,0,0.5)",
                }}
              >
                {/* Drawer header */}
                <div
                  className="sticky top-0 z-10 flex items-center justify-between px-5 sm:px-8 py-5"
                  style={{ background: "var(--bg-primary)", borderBottom: "1px solid var(--border-color)" }}
                >
                  <div className="flex items-center gap-3">
                    <XHunterLogo size="sm" />
                    <div className="h-6 w-px" style={{ background: "var(--border-color)" }} />
                    <h2 className="font-display font-bold text-base" style={{ color: "var(--text-secondary)" }}>
                      {forgotMode !== "idle"
                        ? "Восстановление"
                        : activePanel === "login" ? "Вход" : "Регистрация"}
                    </h2>
                  </div>
                  <button
                    onClick={closePanel}
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-color)" }}
                    aria-label="Закрыть"
                  >
                    <XIcon size={15} style={{ color: "var(--text-muted)" }} />
                  </button>
                </div>

                {/* Accent line */}
                <div
                  className="h-[2px] w-full"
                  style={{ background: "linear-gradient(90deg, var(--accent), var(--magenta), transparent)", opacity: 0.65 }}
                />

                {/* Form body */}
                <div className="px-5 sm:px-8 py-7">
                  <AnimatePresence mode="wait">
                    {forgotMode !== "idle" ? (
                      <motion.div key="forgot" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.25 }}>
                        {forgotMode === "sent" ? (
                          <div className="text-center py-8">
                            <motion.div
                              initial={{ scale: 0 }} animate={{ scale: 1 }}
                              transition={{ type: "spring", stiffness: 300, delay: 0.1 }}
                              className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-5"
                              style={{ background: "rgba(61,220,132,0.1)", border: "1px solid rgba(61,220,132,0.25)" }}
                            >
                              <Mail size={22} style={{ color: "var(--success)" }} />
                            </motion.div>
                            <h3 className="font-display font-bold text-lg mb-2" style={{ color: "var(--text-primary)" }}>Письмо отправлено</h3>
                            <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
                              Проверьте <strong style={{ color: "var(--text-secondary)" }}>{forgotEmail}</strong><br />и следуйте инструкциям.
                            </p>
                            <button onClick={() => { setForgotMode("idle"); setForgotEmail(""); }} className="flex items-center gap-1.5 text-sm font-medium transition-opacity hover:opacity-80" style={{ color: "var(--accent)" }}>
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
                              Вернуться ко входу
                            </button>
                          </div>
                        ) : (
                          <div>
                            <button onClick={() => setForgotMode("idle")} className="flex items-center gap-1.5 text-sm font-medium mb-6 transition-colors hover:opacity-80" style={{ color: "var(--text-secondary)" }}>
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
                              Назад
                            </button>
                            <h3 className="font-display font-bold text-xl mb-1.5" style={{ color: "var(--text-primary)" }}>Забыли пароль?</h3>
                            <p className="text-sm mb-6" style={{ color: "var(--text-muted)", lineHeight: 1.7 }}>Введите email — пришлём ссылку для сброса.</p>
                            <label className="vh-label">Email</label>
                            <div className="relative mb-4">
                              <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                              <input type="email" value={forgotEmail} onChange={(e) => setForgotEmail(e.target.value)} className="vh-input pl-10 w-full" placeholder="Ваш email" autoComplete="email" />
                            </div>
                            <Button variant="primary" fluid loading={forgotLoading} disabled={!forgotEmail.trim()} icon={<Mail size={15} />} onClick={handleForgot}>
                              Отправить ссылку
                            </Button>
                          </div>
                        )}
                      </motion.div>
                    ) : (
                      <motion.div key="main" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} transition={{ duration: 0.25 }}>
                        {error && (
                          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-2 rounded-xl p-3 text-sm mb-5" style={{ background: "rgba(229,72,77,0.08)", border: "1px solid rgba(229,72,77,0.2)", color: "var(--danger)" }}>
                            <AlertCircle size={16} />{error}
                          </motion.div>
                        )}

                        {/* SSO */}
                        <div className="mb-5">
                          <div className="flex gap-3">
                            {SSO_BUTTONS.map(({ label, endpoint, icon }) => (
                              <motion.button key={label} type="button" className="flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }} whileHover={{ borderColor: "var(--border-hover)" }} whileTap={{ scale: 0.97 }} onClick={() => handleSso(endpoint, label)}>
                                {icon}{label}
                              </motion.button>
                            ))}
                          </div>
                          <div className="flex items-center gap-3 mt-4">
                            <div className="flex-1 h-px" style={{ background: "var(--border-color)" }} />
                            <span className="text-sm" style={{ color: "var(--text-muted)" }}>или через email</span>
                            <div className="flex-1 h-px" style={{ background: "var(--border-color)" }} />
                          </div>
                        </div>

                        <form onSubmit={handleSubmit} className="space-y-4">
                          {activePanel === "register" && (
                            <div>
                              <label className="vh-label">Полное имя</label>
                              <div className="relative">
                                <User size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                                <input type="text" value={fullName} onChange={(e) => { setFullName(e.target.value); try { sessionStorage.setItem("vh-auth-name", e.target.value); } catch {} }} required className="vh-input pl-10 w-full" placeholder="Иван Петров" autoComplete="name" />
                              </div>
                            </div>
                          )}

                          <div>
                            <label className="vh-label">Email</label>
                            <div className="relative">
                              <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
                              <input type="email" value={email} onChange={(e) => { setEmail(e.target.value); try { sessionStorage.setItem("vh-auth-email", e.target.value); } catch {} }} required className="vh-input pl-10 w-full" placeholder="Ваш email" autoComplete="email" />
                            </div>
                          </div>

                          <div>
                            <div className="flex items-center justify-between mb-1">
                              <label className="vh-label mb-0">Пароль</label>
                              {activePanel === "login" && (
                                <button type="button" onClick={() => setForgotMode("form")} className="text-sm transition-colors hover:opacity-80" style={{ color: "var(--accent)" }}>Забыли пароль?</button>
                              )}
                            </div>
                            <PasswordInput id="panel-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={activePanel === "register" ? "Минимум 8 символов" : "Введите пароль"} autoComplete={activePanel === "login" ? "current-password" : "new-password"} ariaLabel="Пароль" />
                            {activePanel === "register" && <PasswordChecklist value={password} />}
                          </div>

                          {activePanel === "register" && (
                            <div>
                              <label className="vh-label">Повторите пароль</label>
                              <PasswordInput id="panel-confirm-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Введите пароль ещё раз" autoComplete="new-password" ariaLabel="Подтвердите пароль" />
                              {!passwordsMatch && <p className="mt-1.5 text-xs" style={{ color: "var(--danger)" }}>Пароли не совпадают</p>}
                            </div>
                          )}

                          {activePanel === "login" && (
                            <label className="flex items-center gap-2.5 cursor-pointer select-none">
                              <div className="relative w-9 h-5 rounded-full cursor-pointer flex-shrink-0" style={{ background: rememberMe ? "var(--accent)" : "var(--input-bg)", border: `1px solid ${rememberMe ? "var(--accent)" : "var(--border-color)"}`, transition: "background 0.2s" }} onClick={() => setRememberMe(!rememberMe)}>
                                <motion.div className="absolute top-0.5 w-3.5 h-3.5 rounded-full bg-white" animate={{ left: rememberMe ? 18 : 2 }} transition={{ type: "spring", stiffness: 500, damping: 30 }} style={{ boxShadow: rememberMe ? "0 0 6px var(--accent-glow)" : "none" }} />
                              </div>
                              <span className="text-xs" style={{ color: "var(--text-muted)" }}>Запомнить меня</span>
                            </label>
                          )}

                          <Button type="submit" variant="primary" fluid loading={loading} disabled={!passwordsMatch} iconRight={<ArrowRight size={16} />}>
                            {activePanel === "login" ? "Войти" : "Зарегистрироваться"}
                          </Button>

                          {activePanel === "register" && (
                            <p className="text-center text-sm mt-2" style={{ color: "var(--text-muted)" }}>14 дней бесплатно · Без кредитной карты</p>
                          )}
                        </form>

                        <p className="mt-5 text-center text-sm" style={{ color: "var(--text-muted)" }}>
                          {activePanel === "login" ? "Нет аккаунта?" : "Уже есть аккаунт?"}{" "}
                          <button onClick={() => openPanel(activePanel === "login" ? "register" : "login")} className="font-medium" style={{ color: "var(--accent)" }}>
                            {activePanel === "login" ? "Зарегистрироваться" : "Войти"}
                          </button>
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>
    </LandingAuthContext.Provider>
  );
}
