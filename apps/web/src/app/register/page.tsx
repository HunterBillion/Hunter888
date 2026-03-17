"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { setTokens } from "@/lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = await api.post("/auth/register", {
        email,
        password,
        full_name: fullName,
      });
      setTokens(data.access_token, data.refresh_token);
      router.push("/");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Ошибка регистрации";
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
            РЕГИСТРАЦИЯ
          </h1>
          <p className="mt-2 text-gray-400 text-sm">
            Создайте аккаунт для начала обучения
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="rounded-md bg-vh-red/10 border border-vh-red/30 p-3 text-sm text-vh-red">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="fullName" className="vh-label">
              Полное имя
            </label>
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              className="vh-input"
              placeholder="Иван Петров"
            />
          </div>

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
              minLength={8}
              className="vh-input"
              placeholder="Минимум 8 символов"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="vh-btn-primary w-full"
          >
            {loading ? "Регистрация..." : "Зарегистрироваться"}
          </button>
        </form>

        <p className="text-center text-sm text-gray-500">
          Уже есть аккаунт?{" "}
          <Link href="/login" className="text-vh-purple hover:text-vh-magenta transition-colors">
            Войти
          </Link>
        </p>
      </div>
    </div>
  );
}
