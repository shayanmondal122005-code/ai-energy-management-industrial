"use client"
import { useState, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { facilities, bills, ApiError } from "@/lib/api"

export default function BillsPage() {
  const [facilityId, setFacilityId] = useState("")
  const { data: facilityList = [] } = useQuery({ queryKey: ["facilities"], queryFn: facilities.list })
  useEffect(() => { const first = facilityList[0]; if (first && !facilityId) setFacilityId(first.id) }, [facilityList, facilityId])

  const qc = useQueryClient()
  const { data: billList = [], isLoading } = useQuery({
    queryKey: ["bills", facilityId],
    queryFn: () => bills.list(facilityId),
    enabled: !!facilityId,
  })

  const [form, setForm] = useState({ period: "", units_kwh: "", peak_demand_kw: "", amount_rs: "" })
  const [error, setError] = useState("")
  const fileRef = useRef<HTMLInputElement>(null)

  const upload = useMutation({
    mutationFn: async () => {
      const fd = new FormData()
      fd.append("period", form.period)
      fd.append("units_kwh", form.units_kwh)
      fd.append("amount_rs", form.amount_rs)
      if (form.peak_demand_kw) fd.append("peak_demand_kw", form.peak_demand_kw)
      const f = fileRef.current?.files?.[0]
      if (f) fd.append("file", f)
      return bills.upload(facilityId, fd)
    },
    onSuccess: () => {
      setForm({ period: "", units_kwh: "", peak_demand_kw: "", amount_rs: "" })
      if (fileRef.current) fileRef.current.value = ""
      setError("")
      qc.invalidateQueries({ queryKey: ["bills", facilityId] })
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Upload failed"),
  })

  const upd = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(s => ({ ...s, [k]: e.target.value }))

  // Calibration summary from uploaded bills
  const avgRate = billList.length
    ? (billList.reduce((s, b) => s + (b.effective_rate_rs_kwh ?? 0), 0) / billList.length).toFixed(2)
    : "--"
  const avgBill = billList.length
    ? Math.round(billList.reduce((s, b) => s + b.amount_rs, 0) / billList.length).toLocaleString("en-IN")
    : "--"

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">Electricity Bills</h1>
          <p className="page-sub">Upload past bills · calibrates savings &amp; baseline</p>
        </div>
        {facilityList.length > 1 && (
          <select value={facilityId} onChange={e => setFacilityId(e.target.value)}
            className="bg-panel border border-border text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent">
            {facilityList.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </div>

      {/* Calibration summary */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-panel border border-border rounded-xl p-4">
          <p className="font-mono text-[10px] tracking-[2px] uppercase text-slate-400 mb-1">Bills on file</p>
          <p className="text-2xl font-bold text-white">{billList.length}</p>
        </div>
        <div className="bg-panel border border-border rounded-xl p-4">
          <p className="font-mono text-[10px] tracking-[2px] uppercase text-slate-400 mb-1">Avg effective rate</p>
          <p className="text-2xl font-bold text-white">₹{avgRate}<span className="text-sm text-slate-400">/kWh</span></p>
        </div>
        <div className="bg-panel border border-border rounded-xl p-4">
          <p className="font-mono text-[10px] tracking-[2px] uppercase text-slate-400 mb-1">Avg monthly bill</p>
          <p className="text-2xl font-bold text-white">₹{avgBill}</p>
        </div>
      </div>

      {/* Upload form */}
      <form onSubmit={e => { e.preventDefault(); upload.mutate() }}
        className="bg-panel border border-border rounded-xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-white">Upload a bill</h2>
        {error && <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">{error}</div>}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="font-mono text-[10px] tracking-[2px] uppercase text-slate-300">Period</label>
            <input required value={form.period} onChange={upd("period")} placeholder="May 2026"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="font-mono text-[10px] tracking-[2px] uppercase text-slate-300">Units (kWh)</label>
            <input required type="number" step="any" value={form.units_kwh} onChange={upd("units_kwh")} placeholder="48200"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="font-mono text-[10px] tracking-[2px] uppercase text-slate-300">Peak demand (kW)</label>
            <input type="number" step="any" value={form.peak_demand_kw} onChange={upd("peak_demand_kw")} placeholder="420"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="font-mono text-[10px] tracking-[2px] uppercase text-slate-300">Amount (₹)</label>
            <input required type="number" step="any" value={form.amount_rs} onChange={upd("amount_rs")} placeholder="312000"
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-accent" />
          </div>
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-[2px] uppercase text-slate-300">Bill file (PDF/image, optional)</label>
          <input ref={fileRef} type="file" accept=".pdf,.png,.jpg,.jpeg"
            className="w-full text-sm text-slate-300 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-accent file:text-white file:text-sm" />
        </div>
        <button type="submit" disabled={upload.isPending}
          className="bg-accent hover:bg-blue-500 text-white rounded-lg px-5 py-2.5 text-sm font-medium transition-colors disabled:opacity-50">
          {upload.isPending ? "Uploading..." : "Upload bill"}
        </button>
      </form>

      {/* Bills list */}
      <div>
        <p className="sec-label">Uploaded Bills</p>
        {isLoading && <p className="text-slate-400 text-sm py-6 text-center">Loading...</p>}
        {!isLoading && !billList.length && (
          <div className="empty-state">No bills uploaded yet — add your first one above.</div>
        )}
        {!!billList.length && (
          <div className="bg-panel border border-border rounded-xl overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border">
                <tr className="font-mono text-[10px] tracking-widest uppercase text-slate-300">
                  {["Period", "Units", "Peak kW", "Amount", "₹/kWh", "File"].map(h => <th key={h} className="text-left px-4 py-3">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {billList.map(b => (
                  <tr key={b.id} className="border-b border-border/50">
                    <td className="px-4 py-3 text-white">{b.period}</td>
                    <td className="px-4 py-3 text-slate-300 font-mono">{b.units_kwh.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-slate-300 font-mono">{b.peak_demand_kw ?? "—"}</td>
                    <td className="px-4 py-3 text-slate-300 font-mono">₹{b.amount_rs.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-emerald-400 font-mono">₹{b.effective_rate_rs_kwh ?? "—"}</td>
                    <td className="px-4 py-3">
                      {b.has_file
                        ? <a href={bills.fileUrl(facilityId, b.id)} target="_blank" className="text-accent hover:underline">view</a>
                        : <span className="text-slate-500">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
