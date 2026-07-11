# HE RTAB-Map Static Map Reload

Date: 2026-07-11 22:32-22:42 CST

Status: static same-scene read-only reload passed; moving and displaced-start
relocalization remain unverified

## Safety Scope

Both runs used `he-visual-slam-shadow`, which contains no `MovementManager` or
`HEConnection`. `/he/nav_cmd_vel` had zero publishers. `he-dimos-sense` was
stopped only to release the bounded Rerun port; Aurora remained the local sensor
source. No vehicle command or movement was requested.

## Mode Contract

Commit `52bd9f01` introduced explicit modes. `mapping` refuses an existing
explicit database. `localization` requires an existing non-empty readable
SQLite database with the RTAB-Map `Admin`, `Data`, `Info` and `Node` schema and
forces:

- `Mem/IncrementalMemory=false`;
- `Mem/InitWMWithAllNodes=true`;
- `Mem/LocalizationReadOnly=true`;
- `Mem/LocalizationDataSaved=false`.

The first Orin launch exposed a ROS type mismatch: RTAB-Map 0.23.7 declares
these algorithm parameters as strings. Bool overrides raised
`InvalidParameterTypeException` before a database was created. Commit
`90a62150` preserved explicit YAML string scalars in argv. A bounded native
probe and the full rerun confirmed the corrected values.

## Mapping Run

The corrected mapping run created only:

`/var/tmp/he-rtabmap/he-static-reload-20260711-2237-v2.db`

Final database evidence:

- size: 659456 bytes;
- SHA-256: `144b31d0174ab3f4b743530006664ca5fb37e9f30b7e50392d7bc40bb0cd7e7f`;
- SQLite integrity: `ok`;
- Node rows: 1;
- Link rows: 0;
- Statistics rows: 149.

The low node count is expected for a stationary run with 0.1m/0.1rad commit
thresholds. It confirms that static frame jitter was not persisted as map
nodes.

Thirty-second mapping odometry evidence:

- 171 samples at 5.65Hz;
- zero tracking losses;
- 242 median and 196 minimum inliers;
- 101.59/116.02ms median/P95 latency;
- 3.51/5.96mm final/maximum position drift;
- 0.257m accumulated frame-to-frame motion.

The map was 83x60 at 0.05m, with 2.851% known cells, 17 free cells and 125
occupied cells. It remains below the 10% known-space admission threshold and
was withheld from planners.

## Read-Only Localization Run

The same database was loaded with the four localization overrides visible in
the native process argv and startup log. RTAB-Map reported:

- database version 0.23.7;
- `Localization mode (Mem/IncrementalMemory=false)`;
- restoration of the last saved map correction against nearest node 1;
- `Localization was good`, followed by the default odometry-cache request for
  another, more accurate confirmation.

The loaded map exactly matched the mapping output: 83x60, 2.851% known, 17 free
and 125 occupied cells. Thirty-second localization odometry evidence contained:

- 155 samples at 5.14Hz;
- zero tracking losses;
- 241.5 median and 208 minimum inliers;
- 101.53/115.81ms median/P95 latency;
- 3.43/5.34mm final/maximum position drift;
- 0.223m accumulated frame-to-frame motion.

The database size, mtime and SHA-256 were identical before localization,
during localization and after normal SIGTERM shutdown. A final read-only
SQLite check again returned `integrity_check=ok`, one Node and 149 Statistics
rows. No `Memory::addLink`, type exception, fatal, traceback, native process,
watchdog or Rerun port remained.

## Closeout And Limits

`he-dimos-sense` was restored active with zero restarts. The live RGB, depth,
IR, point-cloud and IMU gate passed; sampled depth validity was 27.9%. The
independent read-only gate returned 0 and navigation publishers remained zero.

This closes safe database creation and same-scene read-only loading. It does
not prove displaced-start relocalization, recovery after tracking loss, loop
closure accuracy, moving ATE/RPE or navigation-usable map coverage. Those gates
still require a new vehicle-down safety confirmation and a richer mapped area.
