# Hosted browser-cache comparison — 3 August 2026

## Decision

Keep the existing 5,000-node in-memory LRU and use native immutable HTTP
caching as the persistent second tier. Do not ship Cache Storage or IndexedDB
for this representative experiment.

The decisive measurement was a direct revisit to bounded node 1907. The cold
response took 308.8 ms and transferred 1,490 bytes (1,190 encoded; 8,690
decoded). Reloading the same immutable version took 0.3 ms and transferred zero
bytes. Cache Storage and IndexedDB were both fast, but neither produced a
material improvement over that browser-native hit, and both add JavaScript
write, quota, garbage-collection, corruption, and upgrade paths.

## Fair one-response comparison

| Strategy | Read/revisit | Transfer | Persistent bytes | Write / maintenance | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Immutable HTTP cache | 0.3 ms warm revisit | 0 bytes | Browser-managed | No application write | Selected |
| Cache Storage | 0.7 ms API read | Avoids network after application lookup | 9,569-byte usage delta | 1.2 ms write; 0.2 ms delete | No material benefit |
| IndexedDB | 0.4 ms record read | Avoids network after application lookup | 22,789-byte usage delta for one current and one stale record | 0.7 ms writes; 1.6 ms v1-to-v2 upgrade; 0.8 ms version GC; 0.4 ms database delete | No material benefit |

All three measurements used one complete bounded response of 8,690 decoded
bytes. Neither application-managed alternative stored the packed artifact or an
unbounded username corpus.

## IndexedDB failure and lifecycle assessment

- Lookup would have to be asynchronous and opportunistic so it never delays the
  first network render.
- A schema version and compound key would be required for dataset version, node
  id, record kind, and normalized filter. The measured v1-to-v2 upgrade took
  1.6 ms for the tiny sample; larger migrations remain unmeasured.
- Dataset-version GC removed the synthetic stale record in 0.8 ms.
- A malformed record was detected and deleted without poisoning the current
  record.
- `navigator.storage.estimate()` reported roughly 10.74 GB quota in this
  browser profile, but quota is browser/profile/device-specific and is not an
  entitlement.
- Private/incognito denial, provider eviction, and a real quota-exceeded write
  were not forced. The required fallback is therefore HTTP plus the in-memory
  LRU, which is already the selected design.
- Persisting filtered overlays would multiply records and write amplification.
  They should remain memory-only unless a future trace proves a meaningful
  revisit benefit.

## Publication cleanup

HTTP entries are keyed by immutable dataset-version URLs and naturally stop
matching after a version change. They can expire under ordinary browser cache
policy without an application migration. Cache Storage and IndexedDB both need
explicit old-version deletion; their cleanup paths passed on the synthetic
record, but that machinery does not earn its cost in this slice.

The underlying measurements are recorded in
[`HOSTED_OPENING_SERVICE_BENCHMARK_2026-08-03.json`](HOSTED_OPENING_SERVICE_BENCHMARK_2026-08-03.json).
