"use client"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { auth } from "@/lib/api"

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail]       = useState("")
  const [password, setPassword] = useState("")
  const [error, setError]       = useState("")
  const [loading, setLoading]   = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const data = await auth.login(email, password)
      localStorage.setItem("access_token",  data.access_token)
      localStorage.setItem("refresh_token", data.refresh_token)
      router.push("/dashboard")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="text-2xl font-bold text-white tracking-tight">MicroGrid AI</div>
          <div className="font-mono text-[10px] tracking-[4px] uppercase text-muted mt-1">
            India Energy Intelligence
          </div>
        </div>

        <form onSubmit={handleSubmit} className="bg-panel border border-border rounded-xl p-8 space-y-5">
          <h1 className="text-lg font-semibold text-white">Sign in</h1>

          {error && (
            <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          <div className="space-y-1">
            <label className="font-mono text-[10px] tracking-[2px] uppercase text-muted">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              className="w-full bg-bg border border-border rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-accent"
              placeholder="admin@hospital.in"
            />
          </div>

          <div className="space-y-1">
            <label className="font-mono text-[10px] tracking-[2px] uppercase text-muted">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              className="w-full bg-bg border border-border rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-accent"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-accent hover:bg-blue-500 text-white rounded-lg py-2.5 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <p className="text-center font-mono text-[10px] text-muted mt-6">
          MicroGrid AI v2.0 · India-native · IEC 61850
        </p>
      </div>
    </div>
  )
}
