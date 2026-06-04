/**
 * Supabase Realtime hooks — live updates without polling.
 * Subscribes to facility-scoped channels for readings, alerts, grid changes.
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

// Lazily create the client on first use in the browser.
// Avoids crashing at build time / during static prerender when env vars are absent.
let _supabase: SupabaseClient | null = null;
function getSupabase(): SupabaseClient | null {
  if (typeof window === "undefined") return null;
  if (_supabase) return _supabase;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;
  _supabase = createClient(url, key);
  return _supabase;
}

export function useLiveReadings(facilityId: string) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!facilityId) return;
    const supabase = getSupabase();
    if (!supabase) return;

    const channel = supabase
      .channel(`facility:${facilityId}:readings`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "readings",
          filter: `facility_id=eq.${facilityId}`,
        },
        () => {
          // Invalidate live + history queries — TanStack Query will refetch
          queryClient.invalidateQueries({ queryKey: ["live", facilityId] });
          queryClient.invalidateQueries({ queryKey: ["history", facilityId] });
        }
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [facilityId, queryClient]);
}

export function useLiveAlerts(facilityId: string, onNewAlert?: (alert: unknown) => void) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!facilityId) return;
    const supabase = getSupabase();
    if (!supabase) return;

    const channel = supabase
      .channel(`facility:${facilityId}:alerts`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "alerts",
          filter: `facility_id=eq.${facilityId}`,
        },
        (payload) => {
          queryClient.invalidateQueries({ queryKey: ["alerts", facilityId] });
          onNewAlert?.(payload.new);
        }
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [facilityId, queryClient, onNewAlert]);
}

export function useLiveGridState(facilityId: string) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!facilityId) return;
    const supabase = getSupabase();
    if (!supabase) return;

    const channel = supabase
      .channel(`facility:${facilityId}:grid`)
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "grid_state",
          filter: `facility_id=eq.${facilityId}`,
        },
        () => {
          queryClient.invalidateQueries({ queryKey: ["grid-state", facilityId] });
        }
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [facilityId, queryClient]);
}
