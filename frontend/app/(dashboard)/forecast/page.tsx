"use client"
import { useQuery } from "@tanstack/react-query"
import { useState, useEffect } from "react"
import { facilities } from "@/lib/api"
import { MetricCard } from "@/components/dashboard/MetricCard"
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine,
} from "recharts"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

function useForecast(facilityId: string) {
  return useQuery({
    queryKey: ["forecast", facilityId],
    queryFn: async () => {
      const token = localStorage.getItem("access_token")
      const r = await fetch(`${BASE}/facilities/${facilityId}/forecast/24h`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!r.ok) throw new Error("Forecast failed")
      return r.json()
    },
    enabled: !!facilityId,
    staleTime: 300_000,
  })
}

export default function ForecastPage() {
  const [facilityId, setFacilityId] = useState("")
  const { data: facilityList = [] } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })
  useEffect(() => { const first = facilityList[0]; if (first && !facilityId) setFacilityId(first.id) }, [facilityList, facilityId])

  const { data, isLoading, error } = useForecast(facilityId)

  const chartData = data?.forecast?.map((f: { timestamp: string; forecast_kw: number; solar_kw: number; soc_pct: number }) => ({
    time      : new Date(f.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }),
    load_kw   : Math.round(f.forecast_kw),
    solar_kw  : Math.round(f.solar_kw),
    net_kw    : Math.round(f.solar_kw - f.forecast_kw),
    soc_pct   : Math.round(f.soc_pct),
  })) ?? []

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">AI Forecast</h1>
          <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
            XGBoost · 24-hour ahead · Confidence bands
          </p>
        </div>
        {facilityList && facilityList.length > 1 && (
          <select value={facilityId} onChange={e => setFacilityId(e.target.value)}
            className="bg-panel border border-border text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent">
            {facilityList.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </div>

      {/* Accuracy metrics */}
      {data && (
        <div className="grid grid-cols-3 gap-3">
          <MetricCard label="Model Accuracy" value={`${data.accuracy_pct}%`}  color="green"  sub={`MAPE ${data.mape_pct}%`} />
          <MetricCard label="MAE"            value={`${data.mae_kw} kW`}       color="blue"   sub="mean absolute error" />
          <MetricCard label="Horizon"        value="24 hours"                   color="purple" sub="ahead" />
        </div>
      )}

      {isLoading && <div className="text-muted text-sm py-12 text-center">Generating forecast...</div>}
      {error    && <div className="text-red-400 text-sm py-4 text-center">Forecast unavailable — need 48+ hours of readings</div>}

      {/* Load + Solar chart */}
      {chartData.length > 0 && (
        <>
          <div>
            <p className="sec-label">Load vs Solar Forecast — Next 24 Hours</p>
            <div className="bg-panel border border-border rounded-xl p-4">
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="load"  x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="solar" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1c2d47" />
                  <XAxis dataKey="time" tick={{ fill: "#3d5a80", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#3d5a80", fontSize: 11 }} unit=" kW" />
                  <Tooltip contentStyle={{ background: "#0b1120", border: "1px solid #1c2d47", borderRadius: 8 }} />
                  <Legend wrapperStyle={{ color: "#4a6fa5", fontSize: 12 }} />
                  <ReferenceLine y={420} stroke="rgba(239,68,68,0.4)" strokeDasharray="4 4" label={{ value: "Demand limit", fill: "#ef4444", fontSize: 10 }} />
                  <Area type="monotone" dataKey="load_kw"  name="AI Load Forecast" stroke="#ef4444" fill="url(#load)"  strokeWidth={2} />
                  <Area type="monotone" dataKey="solar_kw" name="Solar Forecast"    stroke="#f59e0b" fill="url(#solar)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Battery SoC trace */}
          <div>
            <p className="sec-label">Battery SoC Projection</p>
            <div className="bg-panel border border-border rounded-xl p-4">
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="soc" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#10b981" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1c2d47" />
                  <XAxis dataKey="time" tick={{ fill: "#3d5a80", fontSize: 11 }} />
                  <YAxis domain={[0, 100]} tick={{ fill: "#3d5a80", fontSize: 11 }} unit="%" />
                  <Tooltip contentStyle={{ background: "#0b1120", border: "1px solid #1c2d47", borderRadius: 8 }} />
                  <ReferenceLine y={20} stroke="rgba(239,68,68,0.6)" strokeDasharray="4 4" label={{ value: "Critical 20%", fill: "#ef4444", fontSize: 10 }} />
                  <ReferenceLine y={35} stroke="rgba(245,158,11,0.5)" strokeDasharray="4 4" label={{ value: "Warning 35%", fill: "#f59e0b", fontSize: 10 }} />
                  <Area type="monotone" dataKey="soc_pct" name="Battery SoC" stroke="#10b981" fill="url(#soc)" strokeWidth={2.5} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
