"use client"
import { useState, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { facilities, savings as savingsApi } from "@/lib/api"
import { INDIA_TARIFFS, DEFAULT_TARIFF } from "@/types"

const SYSTEM_COST = 4_000_000  // ₹40L reference system cost for payback

export default function SavingsPage() {
  const [facilityId, setFacilityId] = useState("")
  const { data: facilityList = [] } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })
  useEffect(() => { const first = facilityList[0]; if (first && !facilityId) setFacilityId(first.id) }, [facilityList, facilityId])

  const facility = facilityList?.find(f => f.id === facilityId)
  const tariff   = INDIA_TARIFFS[facility?.state_tariff ?? "West Bengal - CESC"] ?? DEFAULT_TARIFF

  // Realized ("shadow") savings from real history
  const { data: shadow } = useQuery({
    queryKey: ["shadow-savings", facilityId],
    queryFn : () => savingsApi.shadow(facilityId, 30),
    enabled : !!facilityId,
    staleTime: 600_000,
  })

  const measured = shadow?.status === "ok" && shadow.days_evaluated > 0

  // Projection fallback (used only until enough live data exists)
  const batKwh   = facility?.battery_kwh ?? 500
  const peakKw   = 420
  const cheapE   = 8 * (facility?.avg_load_kw ?? 300)
  const arb      = Math.min(cheapE, batKwh) * (tariff.peak - tariff.cheap) * 0.35
  const demSav   = peakKw * 0.15 * tariff.demand_per_kw / 30
  const projDaily = arb + demSav

  const daily   = measured ? shadow!.avg_daily_rs        : projDaily
  const monthly = measured ? shadow!.projected_monthly_rs : projDaily * 30
  const annual  = measured ? shadow!.projected_annual_rs  : projDaily * 365
  const payback = SYSTEM_COST / Math.max(1, monthly)

  const inr = (n: number) => n.toLocaleString("en-IN", { maximumFractionDigits: 0 })

  const CARDS = [
    measured
      ? { label: `Saved · last ${shadow!.days_evaluated}d`, value: `₹${inr(shadow!.total_savings_rs)}`, sub: "measured on your data" }
      : { label: "Daily Saving", value: `₹${inr(daily)}`, sub: "arbitrage + demand charge" },
    { label: measured ? "Avg / day" : "Monthly Saving", value: measured ? `₹${inr(daily)}` : `₹${(monthly / 1000).toFixed(1)}K`, sub: measured ? "per evaluated day" : "projected" },
    { label: "Monthly",  value: `₹${(monthly / 1000).toFixed(1)}K`,    sub: measured ? "projected from avg" : "projected" },
    { label: "Payback",  value: `${payback.toFixed(1)} mo`,            sub: `at ₹${(SYSTEM_COST / 100000).toFixed(0)}L system` },
  ]

  const hours = Array.from({ length: 24 }, (_, h) => ({
    h,
    rate  : tariff.cheap_hours.includes(h) ? tariff.cheap : tariff.peak_hours.includes(h) ? tariff.peak : tariff.normal,
    period: tariff.cheap_hours.includes(h) ? "cheap" : tariff.peak_hours.includes(h) ? "peak" : "normal",
  }))

  const now = new Date().getHours()
  const maxDay = measured ? Math.max(...shadow!.daily.map(d => d.savings_rs), 1) : 1

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">Savings</h1>
          <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
            {measured
              ? `Measured · last ${shadow!.days_evaluated} days of your data`
              : "Projected · connect a meter for measured savings"}
          </p>
        </div>
        {facilityList && facilityList.length > 1 && (
          <select value={facilityId} onChange={e => setFacilityId(e.target.value)}
            className="bg-panel border border-border text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent">
            {facilityList.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </div>

      {/* Mode banner — honest about measured vs projected */}
      <div className={`flex items-center gap-3 rounded-xl px-5 py-3 border ${
        measured ? "bg-emerald-500/7 border-emerald-500/20" : "bg-blue-500/7 border-blue-500/20"
      }`}>
        <span className={measured ? "text-emerald-400 text-lg" : "text-blue-400 text-lg"}>{measured ? "✓" : "ℹ"}</span>
        <p className={`text-sm ${measured ? "text-emerald-400" : "text-blue-400"}`}>
          {measured
            ? `These are realized savings — each past day's actual load and solar replayed through the optimizer.`
            : `Not enough live data yet — showing a projection. Numbers become measured once a meter feeds in real readings.`}
        </p>
      </div>

      {/* Saving cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {CARDS.map(c => (
          <div key={c.label} className="bg-panel border border-border rounded-xl p-5 relative overflow-hidden">
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-emerald-500 to-teal-500" />
            <p className="font-mono text-[9px] tracking-[3px] uppercase text-muted mb-2">{c.label}</p>
            <p className="text-2xl font-bold text-emerald-400 tracking-tight">{c.value}</p>
            <p className="text-xs text-muted mt-1">{c.sub}</p>
          </div>
        ))}
      </div>

      {/* Daily measured savings */}
      {measured && shadow!.daily.length > 0 && (
        <div>
          <p className="sec-label">Daily Savings — Last {shadow!.daily.length} Days</p>
          <div className="bg-panel border border-border rounded-xl p-4">
            <div className="flex gap-1 h-24 items-end">
              {shadow!.daily.map(d => (
                <div key={d.date} className="flex-1 flex flex-col items-center justify-end" title={`${d.date}: ₹${inr(d.savings_rs)} saved (baseline ₹${inr(d.baseline_rs)} → ₹${inr(d.optimized_rs)})`}>
                  <div className="w-full rounded-sm bg-emerald-500/60 hover:bg-emerald-500/80 transition-all"
                       style={{ height: `${(d.savings_rs / maxDay) * 100}%` }} />
                </div>
              ))}
            </div>
            <p className="text-xs text-muted mt-3 font-mono">
              Total ₹{inr(shadow!.total_savings_rs)} over {shadow!.days_evaluated} days · avg ₹{inr(shadow!.avg_daily_rs)}/day
            </p>
          </div>
        </div>
      )}

      {/* Tariff breakdown */}
      <div>
        <p className="sec-label">{tariff.state} — ToD Tariff Rates</p>
        <div className="bg-panel border border-border rounded-xl p-4">
          <div className="flex gap-6 mb-4 text-xs font-mono">
            <span className="text-emerald-400">● Cheap ₹{tariff.cheap}/kWh</span>
            <span className="text-muted">● Normal ₹{tariff.normal}/kWh</span>
            <span className="text-red-400">● Peak ₹{tariff.peak}/kWh</span>
          </div>
          <div className="flex gap-1 h-14 items-end">
            {hours.map(({ h, rate, period }) => (
              <div key={h} className="flex-1 flex flex-col items-center gap-1">
                <div
                  className={`w-full rounded-sm transition-all ${
                    period === "cheap"  ? "bg-emerald-500/60" :
                    period === "peak"   ? "bg-red-500/60" :
                    "bg-blue-500/40"
                  } ${h === now ? "ring-1 ring-white/60" : ""}`}
                  style={{ height: `${(rate / tariff.peak) * 100}%` }}
                  title={`${h}:00 — ₹${rate}/kWh`}
                />
                {h % 6 === 0 && (
                  <span className="font-mono text-[8px] text-muted">{h}:00</span>
                )}
              </div>
            ))}
          </div>
          <p className="text-xs text-muted mt-3 font-mono">
            Demand charge: ₹{tariff.demand_per_kw}/kW · Software fee: ₹40,000/month
          </p>
        </div>
      </div>

      {/* All 5 state tariffs */}
      <div>
        <p className="sec-label">All India State Tariffs</p>
        <div className="bg-panel border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-border">
              <tr className="font-mono text-[10px] tracking-widest uppercase text-muted">
                {["State", "Cheap", "Normal", "Peak", "Demand/kW"].map(h => (
                  <th key={h} className="text-left px-4 py-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.values(INDIA_TARIFFS).map(t => (
                <tr key={t.state} className={`border-b border-border/50 hover:bg-white/2 ${t.state === facility?.state_tariff ? "bg-accent/5" : ""}`}>
                  <td className="px-4 py-3 text-white font-medium">{t.state}</td>
                  <td className="px-4 py-3 text-emerald-400 font-mono">₹{t.cheap}</td>
                  <td className="px-4 py-3 text-blue-400  font-mono">₹{t.normal}</td>
                  <td className="px-4 py-3 text-red-400   font-mono">₹{t.peak}</td>
                  <td className="px-4 py-3 text-muted     font-mono">₹{t.demand_per_kw}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
