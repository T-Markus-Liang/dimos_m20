# HE RTAB-Map Extended Static Shadow Soak

Date: 2026-07-11 20:27-20:37 CST

Status: baseline defect reproduced; boundedness fix pending post-deployment soak

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

The first boundedness patch adds two independent controls:

- `RGBD/LinearUpdate=0.02m` and `RGBD/AngularUpdate=0.01rad` use RTAB-Map's
  native update gate to suppress node commits below observed stationary jitter;
- `he-rtabmap-db-watchdog.sh` limits the active database to 256MiB by default,
  polls every two seconds, and exits with status 42 at the limit so the parent
  runner stops and reaps both native processes.

`HE_RTABMAP_MAX_DB_MIB` can set 1-4096MiB and
`HE_RTABMAP_DB_POLL_SECONDS` can set 1-60 seconds. Invalid or zero values fail
before the shadow stack starts. The hard cap is a failure boundary, not a
rolling map database; reaching it intentionally stops shadow SLAM rather than
silently deleting graph state.

A second 600-second static soak is required after deployment. It must prove
that stationary database growth is materially suppressed and that watchdog,
process cleanup, resource and read-only gates still hold.

## Raw Evidence

- `2026-07-11_2027_extended-shadow-soak.tsv`
- `2026-07-11_2031_extended-shadow-supplement.tsv`
- `2026-07-11_2035_stationary-odom-90s.json`
