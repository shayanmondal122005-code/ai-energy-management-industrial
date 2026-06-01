/**
 * Supabase Realtime hooks — live updates without polling.
 * Subscribes to facility-scoped channels for readings, alerts, grid changes.
 */
import { createClient } from "@supabase/supabase-js";
import { useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

export function useLiveReadings(facilityId: string) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!facilityId) return;

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
