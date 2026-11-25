import { useEffect, useState } from "react";
import type { ApiList } from "./types";

// Keep each response attached to the exact request that produced it.
// Callers memoize load by its scope (dataset, run, or filters).
export function usePage<T>(load: (offset: number) => Promise<ApiList<T>>, enabled = true) {
  const [cursor, setCursor] = useState({ load, offset: 0, revision: 0 });
  if (cursor.load !== load) setCursor({ load, offset: 0, revision: 0 });
  const [result, setResult] = useState<{
    cursor: typeof cursor;
    data?: ApiList<T>;
    error?: Error;
  }>();
  useEffect(() => {
    if (!enabled) return;
    let current = true;
    load(cursor.offset).then(
      (data) => { if (current) setResult({ cursor, data }); },
      (error) => { if (current) setResult({ cursor, error }); },
    );
    return () => { current = false; };
  }, [cursor, load, enabled]);

  const response = result?.cursor === cursor ? result : undefined;
  const limit = response?.data?.page.limit ?? 100;
  const move = (offset: number) => setCursor({ load, offset, revision: cursor.revision + 1 });
  return {
    items: response?.data?.items ?? [],
    error: response?.error,
    loading: enabled && !response,
    offset: cursor.offset,
    hasMore: response?.data?.page.has_more ?? false,
    previous: () => move(Math.max(0, cursor.offset - limit)),
    next: () => move(cursor.offset + limit),
    retry: () => move(cursor.offset),
    first: () => move(0),
  };
}
