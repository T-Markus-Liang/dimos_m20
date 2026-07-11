# HE RTAB-Map Extended Static Shadow Soak

Date: 2026-07-11 20:27-20:37 CST

Status: corrected boundedness fix verified in a 600-second static soak

## Safety And Scope

The vehicle remained raised and stationary. The full five-module
`he-visual-slam-shadow` blueprint ran for 600 seconds without
`MovementManager` or `HEConnection`. `/he/nav_cmd_vel` had zero publishers in
every sample. No chassis command, navigation goal or exploration action was
issued.

After shutdown, `he-dimos-sense.service` and `aurora930.service` were active
with zero restarts, no RTAB-Map process remained, and the independent
`verify-he-readonly.sh` gate passed.

## Runtime Results

The primary sampler covered 590 seconds of the requested 600-second run:

| Metric | Start | Minimum/maximum | End |
|---|---:|---:|---:|
| available memory | 3404.7MiB | minimum 3179.9MiB | 3204.1MiB |
| swap used | 529.5MiB | maximum 533.2MiB | 533.2MiB |
| RTAB-Map RSS | 436.7MiB | maximum 554.8MiB | 554.8MiB |
| database | 16.7MiB | maximum 126.7MiB | 126.7MiB |

The overlapping full-stack sampler observed about 1.82-1.84GiB RSS,
132.0-147.1% CPU, 6-23% GPU and a maximum temperature of 64.25C. There was no
OOM, process restart or motion publisher.

## Stationary Odometry

The independent 90-second benchmark collected 348 samples at 3.95Hz with zero
tracking loss. Inliers were 240 median and 202 minimum. Final/max position
drift was 4.72/8.25mm and final/max rotation drift was 0.108/0.249 degrees.
Latency was 152ms median, 215ms P95 and 398ms maximum; estimation time was
126ms median and 152ms P95.

Despite the small net drift, accumulated frame-to-frame position motion was
0.480m. RTAB-Map therefore kept committing stationary jitter as graph nodes.
The database gained 110.0MiB in 590 seconds, about 11.2MiB/minute, and was not
bounded by the existing five-file retention policy. That policy limits file
count between runs, not the size of the active database.

## Corrective Design

The first boundedness patch added two independent controls:

- `RGBD/LinearUpdate=0.02m` and `RGBD/AngularUpdate=0.01rad` attempted to use
  RTAB-Map's native update gate to suppress stationary commits;
- `he-rtabmap-db-watchdog.sh` limits the active database to 256MiB by default,
  polls every two seconds, and exits with status 42 at the limit so the parent
  runner stops and reaps both native processes.

`HE_RTABMAP_MAX_DB_MIB` can set 1-4096MiB and
`HE_RTABMAP_DB_POLL_SECONDS` can set 1-60 seconds. Invalid or zero values fail
before the shadow stack starts. The hard cap is a failure boundary, not a
rolling map database; reaching it intentionally stops shadow SLAM rather than
silently deleting graph state.

The first Orin deployment disproved the threshold assumption. Both parameters
were loaded, but the database reached 33.1MiB after 121 seconds. RTAB-Map 0.23.7
source then showed that both defaults are already 0.1 and that rehearsal occurs
before the movement gate. The default `Mem/NotLinkedNodesKept=true` persists
rehearsed and deleted nodes, so lowering the motion thresholds increased update
frequency without addressing the write source.

The corrected patch explicitly restores 0.1m/0.1rad and sets
`Mem/NotLinkedNodesKept=false`. Linked map nodes and their binary RGB-D data
remain available; only nodes rejected or merged before graph linkage stop being
retained. The independent 256MiB watchdog remains the final hard boundary.
This corrected configuration first passed a 110-second uncontaminated slope
window, then completed the full detached 600-second static soak.

## Corrected 600-Second Result

The corrected primary sampler covered 590 seconds with 55 samples. The active
database grew from 344,064 to 1,458,176 bytes: 1.06MiB net or about
0.108MiB/minute. The baseline gained about 110.0MiB in the same window, so
active-database growth fell by about 99.0%. The result is materially suppressed
but not mathematically zero; the 256MiB watchdog remains required for long-term
fault containment.

| Metric | Corrected result |
|---|---:|
| available memory | 3.18-3.30GiB, 3.23GiB average |
| swap growth | 0 bytes |
| RTAB-Map RSS | 439-509MiB, 481MiB average |
| full stack RSS | 1.68-1.77GiB, 1.73GiB average |
| full stack CPU | 121.8-156.1%, 134.2% average |
| GPU | 6-26%, 11.0% average |
| maximum temperature | 63.28C |
| navigation publishers | 0 in every sample |

Normal shutdown removed both native processes and restored
`he-dimos-sense.service` and `aurora930.service` active with zero restarts. The
in-script final read-only gate initially saw a temporary extra Aurora
subscription from its own sensor verifier. After DDS convergence, an
independent `verify-he-readonly.sh` passed with no localization/navigation
process and zero `/he/nav_cmd_vel` publishers.

## Test-Orchestration Findings

Two failed attempts were not hidden:

- keeping an SSH output pipe attached to the very verbose native processes
  caused exit status 141 when the connection closed; detached runs must redirect
  stdout/stderr locally on Orin;
- an earlier timer-owned soak survived its SSH connection and later stopped a
  newer run during its cleanup. Before a new soak, verify there is exactly one
  `/tmp/run-shadow-soak.sh` restore owner.

These failures affected test orchestration, not the final detached soak. The
second issue briefly caused one `he-dimos-sense` restart during overlapping
restore attempts. After all stale owners exited, the service was stabilized,
the explained counter reset, and both live sensor and independent read-only
gates passed before the final run.

A second 600-second static soak is required after deployment. It must prove
that stationary database growth is materially suppressed and that watchdog,
process cleanup, resource and read-only gates still hold.

## Raw Evidence

- `2026-07-11_2027_extended-shadow-soak.tsv`
- `2026-07-11_2031_extended-shadow-supplement.tsv`
- `2026-07-11_2035_stationary-odom-90s.json`
- `2026-07-11_2051_first-threshold-failed.tsv`
- `2026-07-11_2051_first-threshold-supplement.tsv`
- `2026-07-11_2105_bounded-shadow-soak.tsv`
- `2026-07-11_2105_bounded-shadow-supplement.tsv`
