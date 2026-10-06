"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { post } from "@/lib/api";
import { useAuth } from "@/store/auth";

interface Tokens { access_token: string; refresh_token: string }

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const setTokens = useAuth((s) => s.setTokens);
  const [f, setF] = useState({ identifier: "", email: "", username: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let identifier = f.identifier;
      if (mode === "register") {
        await post("/api/auth/register", { email: f.email, username: f.username, password: f.password }, false);
        identifier = f.username;
      }
      const t = await post<Tokens>("/api/auth/login", { identifier, password: f.password }, false);
      setTokens(t.access_token, t.refresh_token);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message.replace(/^\[.*"msg":"([^"]+)".*$/, "$1"));
      setBusy(false);
    }
  }

  const field = "w-full rounded-lg border border-line bg-raise px-3 py-2 outline-none focus:border-accent";
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <form onSubmit={submit} className="space-y-4" data-testid={`${mode}-form`}>
      <h1 className="text-2xl font-semibold">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
      {mode === "login" ? (
        <div><label htmlFor="identifier" className="mb-1 block text-sm text-muted">Username or email</label>
          <input id="identifier" className={field} autoComplete="username" required value={f.identifier} onChange={set("identifier")} /></div>
      ) : (
        <>
          <div><label htmlFor="email" className="mb-1 block text-sm text-muted">Email</label>
            <input id="email" type="email" className={field} autoComplete="email" required value={f.email} onChange={set("email")} /></div>
          <div><label htmlFor="username" className="mb-1 block text-sm text-muted">Username</label>
            <input id="username" className={field} autoComplete="username" required minLength={3} maxLength={32} pattern="[A-Za-z0-9_]+" title="Letters, digits and underscore" value={f.username} onChange={set("username")} /></div>
        </>
      )}
      <div><label htmlFor="password" className="mb-1 block text-sm text-muted">Password</label>
        <input id="password" type="password" className={field} autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "register" ? 8 : 1} value={f.password} onChange={set("password")} /></div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <button disabled={busy} data-testid="auth-submit" className="w-full rounded-full bg-accent py-2.5 font-semibold text-ink disabled:opacity-50">
        {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
      </button>
      <p className="text-center text-sm text-muted">
        {mode === "login" ? <>No account? <Link className="text-accent underline" href="/register">Register</Link></> : <>Have an account? <Link className="text-accent underline" href="/login">Sign in</Link></>}
      </p>
    </form>
  );
}
