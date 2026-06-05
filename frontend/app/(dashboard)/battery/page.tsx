"use client"
import { useQuery } from "@tanstack/react-query"
import { useState, useEffect } from "react"
import { facilities, readings } from "@/lib/api"
import { MetricCard } from "@/components/dashboard/MetricCard"
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts"

export default function BatteryPage() {
  const [facilityId, setFacilityId] = useState("")
  const { data: facilityList = [] } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })
  useEffect(() => { const first = facilityList[0]; if (first && !facilityId) setFacilityId(first.id) }, [facilityList, facilityId])

  const { data: live } = useQuery({
    queryKey: ["live", facilityId],
    queryFn : () => readings.live(facilityId),
    enabled : !!facilityId,
    refetchInterval: 30_000,
  })

  const facility = facilityList?.find(f => f.id === facilityId)
  const soc      = live?.battery_soc ?? 0
  const socColor: "green" | "amber" | "red" = soc >= 35 ? "green" : soc >= 20 ? "amber" : "red"

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Battery Monitor</h1>
          <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
            Coulomb counting · Arrhenius degradation · SoH tracking
          </p>
        </div>
        {facilityList && facilityList.length > 1 && (
          <select value={facilityId} onChange={e => setFacilityId(e.target.value)}
            className="bg-panel border border-border text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent">
            {facilityList.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="State of Charge" value={`${soc.toFixed(0)}%`}                              color={socColor} sub={soc >= 35 ? "Healthy" : soc >= 20 ? "Warning" : "Critical"} />
        <MetricCard label="Capacity"        value={`${facility?.battery_kwh ?? "--"} kWh`}            color="blue"    />
        <MetricCard label="Temperature"     value={`${live?.battery_temp?.toFixed(1) ?? "--"}°C`}     color="amber"   />
        <MetricCard label="Net Power"       value={`${(live?.net_kw ?? 0) > 0 ? "+" : ""}${(live?.net_kw ?? 0).toFixed(0)} kW`} color={(live?.net_kw ?? 0) >= 0 ? "green" : "red"} sub={(live?.net_kw ?? 0) >= 0 ? "Charging" : "Discharging"} />
      </div>

      {/* SoC gauge */}
      <div className="bg-panel border border-border rounded-xl p-6">
        <p className="sec-label !mt-0">State of Charge</p>
        <div className="relative h-6 bg-bg rounded-full overflow-hidden border border-border">
          <div
            className={`h-full rounded-full transition-all duration-1000 ${
              soc >= 35 ? "bg-emerald-500" : soc >= 20 ? "bg-amber-500" : "bg-red-500"
            }`}
            style={{ width: `${soc}%` }}
          />
          <div className="absolute inset-0 flex items-center justify-center font-mono text-xs text-white font-bold">
            {soc.toFixed(1)}%
          </div>
        </div>
        <div className="flex justify-between font-mono text-[9px] text-muted mt-2">
          <span>0%</span>
          <span className="text-red-400">◆ 20% Critical</span>
          <span className="text-amber-400">◆ 35% Warning</span>
          <span>100%</span>
        </div>
      </div>

      <div className="bg-panel border border-border rounded-xl p-5">
        <p className="sec-label !mt-0">Physics Model</p>
        <div className="grid grid-cols-2 gap-3 text-sm">
          {[
            { k: "Coulomb Counting",     v: "Integrates power flow over time to track SoC" },
            { k: "Arrhenius Correction", v: "Capacity reduces 0.5%/°C above 25°C" },
            { k: "Charge Efficiency",    v: "95% round-trip (some energy lost as heat)" },
            { k: "Degradation Model",    v: "Capacity decreases each discharge cycle" },
          ].map(({ k, v }) => (
            <div key={k} className="bg-bg rounded-lg p-3 border border-border">
              <p className="font-mono text-[10px] text-muted tracking-widest uppercase mb-1">{k}</p>
              <p className="text-white text-xs leading-relaxed">{v}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
