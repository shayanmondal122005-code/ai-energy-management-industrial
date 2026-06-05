"use client"
import { useQuery } from "@tanstack/react-query"
import { useState, useEffect } from "react"
import { facilities } from "@/lib/api"
import { INDIA_TARIFFS } from "@/types"

export default function SettingsPage() {
  const [facilityId, setFacilityId] = useState("")
  const { data: facilityList = [] } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })
  useEffect(() => { const first = facilityList[0]; if (first && !facilityId) setFacilityId(first.id) }, [facilityList, facilityId])
  const facility = facilityList?.find(f => f.id === facilityId)

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">Settings</h1>
        <p className="font-mono text-[10px] text-muted tracking-widest uppercase mt-0.5">
          Facility config · Tariff · Notifications
        </p>
      </div>

      {/* Facility info */}
      <div className="bg-panel border border-border rounded-xl p-6 space-y-4">
        <p className="sec-label !mt-0">Facility</p>
        <div className="grid grid-cols-2 gap-4 text-sm">
          {[
            { label: "Name",         value: facility?.name },
            { label: "City",         value: facility?.city },
            { label: "State Tariff", value: facility?.state_tariff },
            { label: "Battery",      value: facility ? `${facility.battery_kwh} kWh` : "--" },
            { label: "Solar Array",  value: facility ? `${facility.solar_kw} kW` : "--" },
            { label: "Avg Load",     value: facility ? `${facility.avg_load_kw} kW` : "--" },
          ].map(({ label, value }) => (
            <div key={label}>
              <p className="font-mono text-[9px] tracking-widest uppercase text-muted mb-1">{label}</p>
              <p className="text-white">{value ?? "--"}</p>
            </div>
          ))}
        </div>
      </div>

      {/* WhatsApp alerts config */}
      <div className="bg-panel border border-border rounded-xl p-6 space-y-4">
        <p className="sec-label !mt-0">WhatsApp Alerts</p>
        <p className="text-sm text-muted">Critical alerts are delivered via WhatsApp within 60 seconds of event.</p>
        <div className="space-y-2">
          <label className="font-mono text-[9px] tracking-widest uppercase text-muted">Your WhatsApp Number</label>
          <input
            type="tel"
            placeholder="+91 98XXX XXXXX"
            className="w-full bg-bg border border-border rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-accent"
          />
        </div>
        <button className="px-5 py-2.5 bg-accent hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
          Save &amp; Verify
        </button>
      </div>

      {/* API info */}
      <div className="bg-panel border border-border rounded-xl p-6 space-y-3">
        <p className="sec-label !mt-0">API Access</p>
        <p className="text-sm text-muted">Use API keys to connect IoT gateways and feeders.</p>
        <div className="bg-bg border border-border rounded-lg px-4 py-3 font-mono text-xs text-muted">
          Facility ID: {facilityId || "—"}
        </div>
        <button className="px-5 py-2.5 border border-border text-muted hover:text-white rounded-lg text-sm transition-colors">
          Generate API Key
        </button>
      </div>
    </div>
  )
}
