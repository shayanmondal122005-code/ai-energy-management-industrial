"use client"
import { useQuery } from "@tanstack/react-query"
import { facilities } from "@/lib/api"

export default function AdminPage() {
  const { data: facilityList } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">Admin</h1>
        <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
          Multi-tenant · User management · Super admin only
        </p>
      </div>

      <div className="bg-panel border border-border rounded-xl p-6 space-y-4">
        <p className="sec-label !mt-0">Facilities</p>
        {facilityList?.map(f => (
          <div key={f.id} className="flex items-center justify-between py-3 border-b border-border/50 last:border-0">
            <div>
              <p className="text-white text-sm font-medium">{f.name}</p>
              <p className="font-mono text-[10px] text-muted">{f.city} · {f.state_tariff}</p>
            </div>
            <div className="text-right font-mono text-xs text-muted">
              <p>{f.battery_kwh} kWh · {f.solar_kw} kW</p>
              <p className={f.is_active ? "text-emerald-400" : "text-red-400"}>
                {f.is_active ? "Active" : "Inactive"}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
