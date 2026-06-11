"use client"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { edge } from "@/lib/api"

const PERIOD_COLOR: Record<string, string> = {
  "PEAK": "text-red-400",
  "OFF-PEAK": "text-emerald-400",
  "NORMAL": "text-yellow-400",
}

function Pill({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
      on ? "bg-emerald-400/15 text-emerald-400" : "bg-slate-700/50 text-slate-500"
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${on ? "bg-emerald-400" : "bg-slate-600"}`} />
      {label}
    </span>
  )
}

function Card({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-panel border border-border rounded-xl p-5 ${className}`}>
      <p className="font-mono text-[10px] tracking-[2px] uppercase text-slate-400 mb-3">{title}</p>
      {children}
    </div>
  )
}

function formatRs(n: number): string {
  if (n >= 100000) return `${(n / 100000).toFixed(2)}L`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toFixed(2)
}

export default function EdgeMonitorPage() {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ["edge-live"],
    queryFn: () => edge.live(),
    refetchInterval: 5000,
  })

  const resetMut = useMutation({
    mutationFn: () => edge.resetSavings(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["edge-live"] }),
  })

  if (isLoading) return <p className="text-slate-400 text-sm py-12 text-center">Connecting to edge device...</p>
  if (error) return <p className="text-red-400 text-sm py-12 text-center">Failed to fetch edge data</p>

  const t = data?.telemetry
  const cmd = data?.commands
  const fc = data?.forecast
  const s = data?.savings

  if (!t) {
    return (
      <div className="max-w-4xl mx-auto">
        <h1 className="text-xl font-bold text-white mb-2">Edge Monitor</h1>
        <p className="page-sub mb-6">Live view of your ESP32 / Wokwi simulation</p>
        <div className="empty-state">No telemetry received yet. Start your Wokwi simulation or connect an ESP32.</div>
      </div>
    )
  }

  const periodClass = PERIOD_COLOR[t.tariff_period] ?? "text-slate-300"
  const modeLabel = t.soc_pct < 15 ? "EMERGENCY" : t.soc_pct >= 90 ? "FULL/STOP"
    : cmd ? "CLOUD BRAIN" : "LOCAL FALLBACK"
  const modeColor = modeLabel === "EMERGENCY" ? "text-red-400"
    : modeLabel === "CLOUD BRAIN" ? "text-blue-400" : "text-yellow-400"

  const savingsPct = s && s.baseline_cost_rs > 0
    ? ((s.total_rs / s.baseline_cost_rs) * 100).toFixed(1)
    : "0.0"

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div>
        <h1 className="text-xl font-bold text-white">Edge Monitor</h1>
        <p className="page-sub">Live view · {t.site_id} · sim hour {t.sim_hour?.toFixed(1)}h</p>
      </div>

      {/* Shadow Savings Hero */}
      {s && s.intervals > 0 && (
        <div className="bg-gradient-to-r from-emerald-900/30 to-blue-900/30 border border-emerald-400/20 rounded-xl p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <p className="font-mono text-[10px] tracking-[2px] uppercase text-emerald-400/80">Shadow Savings</p>
              <p className="text-xs text-slate-400 mt-0.5">What the brain would save vs. buying all from grid</p>
            </div>
            <button onClick={() => resetMut.mutate()}
              className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors px-2 py-1 rounded border border-border hover:border-slate-500">
              Reset
            </button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div>
              <p className="text-3xl font-bold text-emerald-400">₹{formatRs(s.total_rs)}</p>
              <p className="text-xs text-slate-400">Total saved</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{savingsPct}<span className="text-sm text-slate-400">%</span></p>
              <p className="text-xs text-slate-400">Cost reduction</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-300">₹{formatRs(s.baseline_cost_rs)}</p>
              <p className="text-xs text-slate-400">Without system</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-blue-400">₹{formatRs(s.optimized_cost_rs)}</p>
              <p className="text-xs text-slate-400">With system</p>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-yellow-400 font-bold">₹{formatRs(s.solar_rs)}</p>
              <p className="text-[10px] text-slate-400 uppercase tracking-wider">Solar</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-amber-400 font-bold">₹{formatRs(s.arbitrage_rs)}</p>
              <p className="text-[10px] text-slate-400 uppercase tracking-wider">Arbitrage</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-purple-400 font-bold">₹{formatRs(s.demand_rs)}</p>
              <p className="text-[10px] text-slate-400 uppercase tracking-wider">Demand shave</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-red-400 font-bold">₹{formatRs(s.dg_rs)}</p>
              <p className="text-[10px] text-slate-400 uppercase tracking-wider">DG displaced</p>
            </div>
          </div>

          <p className="text-[10px] text-slate-500 mt-3">
            {s.intervals?.toFixed(0)} intervals · {s.sim_hours?.toFixed(1)} sim hours · {s.load_kwh?.toFixed(1)} kWh consumed
          </p>
        </div>
      )}

      {/* Hero stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card title="Battery SoC">
          <p className="text-3xl font-bold text-white">{t.soc_pct.toFixed(1)}<span className="text-lg text-slate-400">%</span></p>
          <div className="mt-2 h-2 bg-slate-700 rounded-full overflow-hidden">
            <div className="h-full rounded-full transition-all duration-500"
              style={{ width: `${t.soc_pct}%`, backgroundColor: t.soc_pct < 20 ? "#f87171" : t.soc_pct < 40 ? "#fbbf24" : "#34d399" }} />
          </div>
        </Card>
        <Card title="Solar">
          <p className="text-3xl font-bold text-yellow-400">{(t.solar_w / 1000).toFixed(1)}<span className="text-lg text-slate-400"> kW</span></p>
        </Card>
        <Card title="Load">
          <p className="text-3xl font-bold text-white">{(t.total_load_w / 1000).toFixed(1)}<span className="text-lg text-slate-400"> kW</span></p>
        </Card>
        <Card title="Tariff">
          <p className={`text-2xl font-bold ${periodClass}`}>{t.tariff_period}</p>
          <p className="text-sm text-slate-400 mt-1">₹{t.tariff_rs_kwh}/kWh</p>
        </Card>
      </div>

      {/* Decision + Relays */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card title="Brain Decision">
          <p className={`text-lg font-bold ${modeColor} mb-3`}>{modeLabel}</p>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-400">Charge source</span>
              <span className="text-white font-medium">{t.charge_source}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Grid charging</span>
              <span className={t.grid_charge_active ? "text-emerald-400" : "text-slate-500"}>{t.grid_charge_active ? "ON" : "OFF"}</span>
            </div>
            {cmd && (
              <div className="flex justify-between">
                <span className="text-slate-400">Battery discharge</span>
                <span className={cmd.battery_discharge ? "text-amber-400" : "text-slate-500"}>{cmd.battery_discharge ? "ON" : "OFF"}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-slate-400">Grid charge power</span>
              <span className="text-white font-mono">{(t.grid_charge_w / 1000).toFixed(1)} kW</span>
            </div>
          </div>
        </Card>

        <Card title="Relay States">
          <div className="flex flex-wrap gap-2">
            <Pill on={t.grid_on} label="Grid" />
            <Pill on={t.solar_on} label="Solar" />
            <Pill on={t.battery_on} label="Battery" />
            <Pill on={t.dg_on} label="DG" />
            <Pill on={t.grid_charge_active} label="Grid Charge" />
          </div>
        </Card>
      </div>

      {/* Circuits */}
      <Card title="Hospital Circuits">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {t.circuits.map((c) => (
            <div key={c.name} className={`rounded-lg border p-3 ${
              c.active ? "border-emerald-400/30 bg-emerald-400/5" : "border-red-400/30 bg-red-400/5"
            }`}>
              <p className="text-sm font-medium text-white">{c.name}</p>
              <p className="text-xs text-slate-400 font-mono">{(c.watts / 1000).toFixed(1)} kW</p>
              <p className={`text-xs font-medium mt-1 ${c.active ? "text-emerald-400" : "text-red-400"}`}>
                {c.active ? "ACTIVE" : "SHED"}
              </p>
            </div>
          ))}
        </div>
      </Card>

      {/* Forecast */}
      {fc && (
        <Card title={`Load Forecast · ${fc.available ? "Active" : `Training (${fc.samples} samples, ${fc.buckets} hours)`}`}>
          {fc.available ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-slate-400">Peak load</p>
                <p className="text-white font-bold">{fc.predicted_peak_kw} kW</p>
              </div>
              <div>
                <p className="text-slate-400">Peak hour</p>
                <p className="text-white font-bold">{fc.peak_hour}:00</p>
              </div>
              <div>
                <p className="text-slate-400">Peak in</p>
                <p className="text-white font-bold">{fc.peak_in_hours?.toFixed(1) ?? "—"}h</p>
              </div>
              <div>
                <p className="text-slate-400">Avg next 3h</p>
                <p className="text-white font-bold">{fc.avg_next_3h_kw} kW</p>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <div className="h-2 flex-1 bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${Math.min(100, (fc.samples / 150) * 100)}%` }} />
              </div>
              <span className="text-xs text-slate-400 whitespace-nowrap">{fc.samples}/150 samples</span>
            </div>
          )}
        </Card>
      )}

      <p className="text-xs text-slate-500 text-right">
        Last update: {t.received_at ? new Date(t.received_at).toLocaleTimeString() : "—"}
      </p>
    </div>
  )
}
