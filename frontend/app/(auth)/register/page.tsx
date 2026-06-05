"use client"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { auth } from "@/lib/api"

function PasswordStrength({ password }: { password: string }) {
  const checks = [
    { label: "10+ characters",       pass: password.length >= 10 },
    { label: "Uppercase letter",      pass: /[A-Z]/.test(password) },
    { label: "Lowercase letter",      pass: /[a-z]/.test(password) },
    { label: "Number",                pass: /\d/.test(password) },
    { label: "Special character",     pass: /[!@#$%^&*()_+\-=\[\]{}|;':",./<>?]/.test(password) },
  ]
  const score = checks.filter(c => c.pass).length
  const color = score <= 2 ? "bg-red-500" : score <= 3 ? "bg-amber-500" : score === 4 ? "bg-blue-500" : "bg-green-500"

  if (!password) return null

  return (
    <div className="space-y-2 mt-2">
      <div className="flex gap-1">
        {[1,2,3,4,5].map(i => (
          <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${i <= score ? color : "bg-border"}`} />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {checks.map(c => (
          <span key={c.label} className={`text-[10px] font-mono flex items-center gap-1 ${c.pass ? "text-green-400" : "text-muted"}`}>
            <span>{c.pass ? "âœ“" : "â—‹"}</span> {c.label}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function RegisterPage() {
  const router = useRouter()
  const [form, setForm] = useState({ email: "", password: "", full_name: "", organization: "" })
  const [error, setError]   = useState("")
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  function update(field: string) {
    return (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [field]: e.target.value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      await auth.register(form.email, form.password, form.full_name, form.organization)
      setSuccess(true)
      setTimeout(() => router.push("/login"), 2500)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-10">
          <div className="text-2xl font-bold text-white tracking-tight">MicroGrid AI</div>
          <div className="font-mono text-[10px] tracking-[4px] uppercase text-muted mt-1">
            India Energy Intelligence
          </div>
        </div>

        {success ? (
          <div className="bg-panel border border-green-500/30 rounded-xl p-8 text-center space-y-3">
            <div className="text-green-400 text-3xl">âœ“</div>
            <p className="text-white font-semibold">Account created!</p>
            <p className="text-sm text-muted">Redirecting to sign in...</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="bg-panel border border-border rounded-xl p-8 space-y-5">
            <h1 className="text-lg font-semibold text-white">Create account</h1>

            {error && (
              <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-3">
                {error}
              </div>
            )}

            <div className="space-y-1">
              <label className="font-mono text-[10px] tracking-[2px] uppercase text-muted">Full name</label>
              <input
                type="text"
                value={form.full_name}
                onChange={update("full_name")}
                required
                minLength={2}
                className="w-full bg-bg border border-border rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-accent"
                placeholder="Dr. Ravi Kumar"
              />
            </div>

            <div className="space-y-1">
              <label className="font-mono text-[10px] tracking-[2px] uppercase text-muted">Organization</label>
              <input
                type="text"
                value={form.organization}
                onChange={update("organization")}
                required
                minLength={2}
                className="w-full bg-bg border border-border rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-accent"
                placeholder="AMRI Hospital, Kolkata"
              />
            </div>

            <div className="space-y-1">
              <label className="font-mono text-[10px] tracking-[2px] uppercase text-muted">Work email</label>
              <input
                type="email"
                value={form.email}
                onChange={update("email")}
                required
                className="w-full bg-bg border border-border rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-accent"
                placeholder="admin@hospital.in"
              />
            </div>

            <div className="space-y-1">
              <label className="font-mono text-[10px] tracking-[2px] uppercase text-muted">Password</label>
              <input
                type="password"
                value={form.password}
                onChange={update("password")}
                required
                minLength={10}
                className="w-full bg-bg border border-border rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-accent"
              />
              <PasswordStrength password={form.password} />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-accent hover:bg-blue-500 text-white rounded-lg py-2.5 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {loading ? "Creating account..." : "Create account"}
            </button>
          </form>
        )}

        <p className="text-center text-sm text-muted mt-6">
          Already have an account?{" "}
          <a href="/login" className="text-accent hover:underline">Sign in</a>
        </p>

        <p className="text-center font-mono text-[10px] text-muted mt-3">
          MicroGrid AI v2.0 Â· India-native Â· IEC 61850
        </p>
      </div>
    </div>
  )
}

