// Metrics recording.

interface MetricPayload {
  name: string;
  value: number;
  timestamp: number;
}

const buffer: MetricPayload[] = [];

/**
 * Record a latency measurement in nanoseconds.
 *
 * Callers in the hot path provide bigint nanosecond values from
 * `process.hrtime.bigint()`. This function accepts `number` for
 * "convenience" — which means every bigint the caller passes is
 * coerced at the boundary.
 */
export function recordLatency(name: string, latencyNs: number): void {
  // --- STRETCH BUG F9: silent type coercion losing precision ---
  // The parameter is typed as `number`. Callers actually have `bigint`
  // values from `process.hrtime.bigint()` and use `Number(hrtime)` or
  // `+hrtime` at the call site. Any value above 2^53 (~9 quadrillion —
  // reachable for cumulative nanosecond counters after ~104 days of
  // uptime) silently loses precision. The code looks correct at the
  // boundary; the loss is invisible until latency charts start lying.
  buffer.push({
    name,
    value: latencyNs,
    timestamp: Date.now(),
  });
}

export function flushMetrics(): MetricPayload[] {
  const out = buffer.slice();
  buffer.length = 0;
  return out;
}
