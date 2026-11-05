# Isolate native-paced evaluation workers from evidence orchestration

## Status

Accepted for validation; a new held-out protocol remains separately gated.

## Context

Issue #22 repeatedly produced invalid native pacing evidence despite numerical agreement, an
accepted macOS time-constraint policy, corrected 20 Hz scheduling, and a persistent parallel
worker pool. An isolated 120-second inference soak passed, while long in-process mission runs
still recorded scheduling overruns as high as 139 ms. One attempt also exposed concurrent
evaluator writes. These failures show that inference implementation, measured mission execution,
protocol supervision, and evidence serialization need distinct ownership.

## Decision

Place a process-isolation seam around every measured native-paced mission. A supervisor owns the
frozen protocol, exclusive execution lease, run ordering, stop rules, and all artifact writes. It
spawns one fresh worker process per measured run. The worker constructs the native runtime,
disables cyclic garbage collection only during the measured interval, executes the existing
wall-clock-paced simulation, and returns the existing `RunResult` plus isolation provenance. The
supervisor serializes and hashes evidence only after the child returns.

Worker failure, wall-timeout, malformed results, and unclean shutdown are explicit errors. A timed
out child is terminated and joined before another worker may start. Native inference backends,
model identity, command selection, safety envelope, numerical tolerance, pacing clock, and pacing
threshold remain unchanged.

## Consequences

Each measured run pays process startup and result-transfer costs outside the measured mission
interval. Large traces temporarily exist in child and supervisor memory during transfer, but no
compression or artifact I/O competes with pacing. Fresh processes prevent accumulated Python GC,
allocator, thread, and scheduler state from crossing run boundaries. The supervisor remains a
single evidence writer, so concurrent evaluators cannot silently interleave bundles.

This architecture improves evidence validity but does not relax the pacing gate or retroactively
validate stopped held-out attempts. A full non-final workload must pass on all four backends before
another untouched held-out set may be reviewed and frozen.
