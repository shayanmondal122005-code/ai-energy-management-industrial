"use client"
import { useQuery } from "@tanstack/react-query"
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

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-panel border border-border rounded-xl p-5">
      <p className="font-mono text-[10px] tracking-[2px] uppercase text-slate-400 mb-3">{title}</p>
      {children}
    </div>
  )
}

export default function EdgeMonitorPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["edge-live"],
    queryFn: () => edge.live(),
    refetchInterval: 5000,
  })

  if (isLoading) return <p className="text-slate-400 text-sm py-12 text-center">Connecting to edge device...</p>
  if (error) return <p className="text-red-400 text-sm py-12 text-center">Failed to fetch edge data</p>

  const t = data?.telemetry
  const cmd = data?.commands
  const fc = data?.forecast

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

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div>
        <h1 className="text-xl font-bold text-white">Edge Monitor</h1>
        <p className="page-sub">Live view · {t.site_id} · sim hour {t.sim_hour?.toFixed(1)}h</p>
      </div>

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
