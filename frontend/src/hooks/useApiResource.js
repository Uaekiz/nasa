import { useEffect, useState } from "react";

// Keyed responses prevent an older request from appearing after a selection change.
export default function useApiResource(load, key) {
  const [result, setResult] = useState(null);
  useEffect(() => {
    if (key === null) return;
    let cancelled = false;
    Promise.resolve().then(load).then(
      (data) => { if (!cancelled) setResult({ key, data }); },
      (error) => { if (!cancelled) setResult({ key, error }); },
    );
    return () => { cancelled = true; };
  }, [load, key]);
  if (key === null) return { loading: false };
  return result?.key === key ? { ...result, loading: false } : { loading: true };
}
