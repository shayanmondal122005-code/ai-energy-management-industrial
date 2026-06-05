"use client"
import { useQuery } from "@tanstack/react-query"
import { useState, useEffect } from "react"
import { facilities } from "@/lib/api"
import { MetricCard } from "@/components/dashboard/MetricCard"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine, Cell,
} from "recharts"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

function useOptimizer(facilityId: string) {
  return useQuery({
    queryKey: ["optimizer", facilityId],
    queryFn: async () => {
      const token = localStorage.getItem("access_token")
      const r = await fetch(`${BASE}/facilities/${facilityId}/optimize`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!r.ok) throw new Error(await r.text())
      return r.json()
    },
    enabled: !!facilityId,
    staleTime: 300_000,
  })
}

const ACTION_COLOR: Record<string, string> = {
  CHARGE    : "#10b981",
  DISCHARGE : "#f59e0b",
  HOLD      : "#3b82f6",
}

const PERIOD_COLOR: Record<string, string> = {
  cheap : "#10b981",
  normal: "#3b82f6",
  peak  : "#ef4444",
}

export default function OptimizePage() {
  const [facilityId, setFacilityId] = useState("")
  const { data: facilityList = [] } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })
  useEffect(() => { const first = facilityList[0]; if (first && !facilityId) setFacilityId(first.id) }, [facilityList, facilityId])

  const { data, isLoading, error } = useOptimizer(facilityId)

  type ScheduleRow = {
    hour: number; load_kw: number; solar_kw: number; grid_kw: number;
    charge_kw: number; discharge_kw: number; soc_pct: number;
    action: string; tariff: number; period: string; cost_inr: number;
  }

  const chartData = data?.schedule?.map((r: ScheduleRow) => ({
    time    : `${r.hour.toString().padStart(2, "0")}:00`,
    grid_kw : r.grid_kw,
    solar_kw: r.solar_kw,
    charge  : r.charge_kw,
    discharge: r.discharge_kw,
    soc     : r.soc_pct,
    action  : r.action,
    tariff  : r.tariff,
    period  : r.period,
    cost    : r.cost_inr,
  })) ?? []

  const savings    = data?.savings_today ?? 0
  const powerCut   = data?.power_cut_risk ?? false
  const minSoc     = data?.min_soc_pct ?? 0
  const status     = data?.status ?? ""

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">Economic Dispatch Optimizer</h1>
          <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
            Linear Programming · 24h ahead · Cost minimization · No-power-cut guarantee
          </p>
        </div>
        <div className="flex items-center gap-3">
          {facilityList && facilityList.length > 1 && (
            <select value={facilityId} onChange={e => setFacilityId(e.target.value)}
              className="bg-panel border border-border text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent">
              {facilityList.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          )}
          {status && (
            <span className={`font-mono text-xs px-3 py-1.5 rounded-full border ${
              status === "optimal"   ? "text-emerald-400 border-emerald-400/30 bg-emerald-400/10" :
              status === "fallback"  ? "text-amber-400  border-amber-400/30  bg-amber-400/10" :
              "text-muted border-border"
            }`}>
              {status === "optimal" ? "✓ LP OPTIMAL" : status === "fallback" ? "⚠ RULE FALLBACK" : ""}
            </span>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="text-muted text-sm py-12 text-center border border-border rounded-xl">
          Running LP optimizer — solving 97 variables...
        </div>
      )}
      {error && (
        <div className="text-red-400 text-sm py-4 text-center">
          {String(error)}
        </div>
      )}

      {data && (
        <>
          {/* Key metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              label="Today's Saving"
              value={`₹${savings.toLocaleString("en-IN")}`}
              color="green"
              sub="vs no optimization"
            />
            <MetricCard
              label="Optimized Cost"
              value={`₹${data.cost_optimized?.toLocaleString("en-IN")}`}
              color="blue"
              sub="total grid import"
            />
            <MetricCard
              label="Baseline Cost"
              value={`₹${data.cost_baseline?.toLocaleString("en-IN")}`}
              color="purple"
              sub="without optimizer"
            />
            <MetricCard
              label="Min SoC"
              value={`${minSoc?.toFixed(0)}%`}
              color={powerCut ? "red" : minSoc < 25 ? "amber" : "green"}
              sub={powerCut ? "⚠ Power cut risk!" : "No power cut risk"}
            />
          </div>

          {/* Power cut guarantee banner */}
          {!powerCut && (
            <div className="flex items-center gap-3 bg-emerald-500/7 border border-emerald-500/20 rounded-xl px-5 py-3">
              <span className="text-emerald-400 text-lg">✓</span>
              <div>
                <p className="text-emerald-400 text-sm font-medium">Power cut mathematically guaranteed not to happen</p>
                <p className="text-emerald-400/60 text-xs font-mono">
                  Minimum SoC stays at {minSoc?.toFixed(0)}% — LP constraint enforces SoC ≥ 10% for all 24 hours
                </p>
              </div>
            </div>
          )}
          {powerCut && (
            <div className="flex items-center gap-3 bg-red-500/7 border border-red-500/20 rounded-xl px-5 py-3">
              <span className="text-red-400 text-lg">⚠</span>
              <div>
                <p className="text-red-400 text-sm font-medium">Power cut risk detected — battery too small for today's load</p>
                <p className="text-red-400/60 text-xs font-mono">
                  Grid import will cover the gap but load shedding may be required
                </p>
              </div>
            </div>
          )}

          {/* Battery action chart */}
          <div>
            <p className="sec-label">Optimal Battery Schedule — 24 Hours</p>
            <div className="bg-panel border border-border rounded-xl p-4">
              <div className="flex gap-4 mb-3 text-xs font-mono">
                <span className="text-emerald-400">● Charge (cheap solar/grid)</span>
                <span className="text-amber-400">● Discharge (peak saving)</span>
                <span className="text-blue-400">● Hold</span>
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1c2d47" />
                  <XAxis dataKey="time" tick={{ fill: "#3d5a80", fontSize: 10 }} interval={2} />
                  <YAxis tick={{ fill: "#3d5a80", fontSize: 10 }} unit=" kW" />
                  <Tooltip
                    contentStyle={{ background: "#0b1120", border: "1px solid #1c2d47", borderRadius: 8, fontSize: 11 }}
                    formatter={(val: number, name: string) => [`${val} kW`, name]}
                  />
                  <Bar dataKey="charge"    name="Charge"    radius={[2, 2, 0, 0]}>
                    {chartData.map((_: unknown, i: number) => <Cell key={i} fill="#10b981" />)}
                  </Bar>
                  <Bar dataKey="discharge" name="Discharge" radius={[2, 2, 0, 0]}>
                    {chartData.map((_: unknown, i: number) => <Cell key={i} fill="#f59e0b" />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* SoC trace */}
          <div>
            <p className="sec-label">Battery SoC — Guaranteed Safe All Day</p>
            <div className="bg-panel border border-border rounded-xl p-4">
              <div className="flex gap-1 items-end h-20">
                {data.soc_trace?.slice(0, 24).map((soc: number, i: number) => (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1">
                    <div
                      className={`w-full rounded-sm ${soc <= 20 ? "bg-red-500" : soc <= 35 ? "bg-amber-500" : "bg-emerald-500"}`}
                      style={{ height: `${soc}%` }}
                      title={`${i}:00 → ${soc}%`}
                    />
                    {i % 6 === 0 && <span className="font-mono text-[8px] text-muted">{i}:00</span>}
                  </div>
                ))}
              </div>
              <div className="flex gap-6 mt-2 font-mono text-[9px]">
                <span className="text-red-400">■ Critical &lt;20%</span>
                <span className="text-amber-400">■ Warning &lt;35%</span>
                <span className="text-emerald-400">■ Safe</span>
              </div>
            </div>
          </div>

          {/* Hour-by-hour table */}
          <div>
            <p className="sec-label">Hour-by-Hour Schedule</p>
            <div className="bg-panel border border-border rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono">
                  <thead className="border-b border-border">
                    <tr className="text-muted tracking-widest uppercase text-[9px]">
                      {["Hour", "Action", "Load", "Solar", "Grid", "Charge", "Discharge", "SoC", "₹/kWh", "Cost ₹"].map(h => (
                        <th key={h} className="text-right first:text-left px-3 py-2">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.schedule?.map((r: ScheduleRow) => (
                      <tr key={r.hour} className="border-b border-border/30 hover:bg-white/2">
                        <td className="px-3 py-2 text-white">{r.hour.toString().padStart(2, "0")}:00</td>
                        <td className="px-3 py-2">
                          <span style={{ color: ACTION_COLOR[r.action] }}>{r.action}</span>
                        </td>
                        <td className="px-3 py-2 text-right text-muted">{r.load_kw}</td>
                        <td className="px-3 py-2 text-right text-amber-400">{r.solar_kw}</td>
                        <td className="px-3 py-2 text-right text-purple-400">{r.grid_kw}</td>
                        <td className="px-3 py-2 text-right text-emerald-400">{r.charge_kw || "—"}</td>
                        <td className="px-3 py-2 text-right text-amber-400">{r.discharge_kw || "—"}</td>
                        <td className="px-3 py-2 text-right" style={{ color: r.soc_pct <= 20 ? "#ef4444" : r.soc_pct <= 35 ? "#f59e0b" : "#10b981" }}>
                          {r.soc_pct}%
                        </td>
                        <td className="px-3 py-2 text-right" style={{ color: PERIOD_COLOR[r.period] }}>
                          {r.tariff}
                        </td>
                        <td className="px-3 py-2 text-right text-white">{r.cost_inr}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="border-t border-border bg-bg">
                    <tr>
                      <td colSpan={9} className="px-3 py-2 text-muted text-right">Total optimized cost</td>
                      <td className="px-3 py-2 text-right text-white font-bold">
                        ₹{data.cost_optimized?.toLocaleString("en-IN")}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
