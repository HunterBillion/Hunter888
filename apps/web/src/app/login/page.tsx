"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { setTokens } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = await api.post("/auth/login", { email, password });
      setTokens(data.access_token, data.refresh_token);
      if (data.must_change_password) {
        router.push("/change-password");
      } else {
        router.push("/");
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Ошибка входа";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="glass-panel w-full max-w-md p-8 space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-display font-bold text-vh-purple tracking-wider">
            VIBEHUNTER
          </h1>
          <p className="mt-2 text-gray-400 text-sm">Войдите в свой аккаунт</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="rounded-md bg-vh-red/10 border border-vh-red/30 p-3 text-sm text-vh-red">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="email" className="vh-label">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="vh-input"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label htmlFor="password" className="vh-label">
              Пароль
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="vh-input"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="vh-btn-primary w-full"
          >
            {loading ? "Вход..." : "Войти"}
          </button>
        </form>

        <p className="text-center text-sm text-gray-500">
          Нет аккаунта?{" "}
          <Link href="/register" className="text-vh-purple hover:text-vh-magenta transition-colors">
            Зарегистрироваться
          </Link>
        </p>
      </div>
    </div>
  );
}
