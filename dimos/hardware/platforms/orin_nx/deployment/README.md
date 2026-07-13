# Orin NX Runtime Templates

This directory owns compute-target deployment only. Robot sensor drivers,
transforms, chassis protocols and blueprints remain under `dimos/robot/<name>`.

Before installing optional GPU dependencies on a Jetson target, generate a
compatibility report:

```bash
mkdir -p ~/dimos-evidence
.venv/bin/python -m dimos.hardware.platforms.orin_nx.compatibility \
  --output ~/dimos-evidence/jetson-compatibility.json
```

See [Jetson compatibility](../../../../../docs/orin-nx/jetson-compatibility.md)
for the qualified matrix and upstream branch assessment.

Validate a deployment without writing files:

```bash
.venv/bin/python -m dimos.hardware.platforms.orin_nx.deployment.install \
  --repo /opt/dimos \
  --profile /etc/dimos/profiles/robot.json \
  --runtime-user dimos \
  --dry-run
```

Install rendered files:

```bash
sudo /opt/dimos/.venv/bin/python -m \
  dimos.hardware.platforms.orin_nx.deployment.install \
  --repo /opt/dimos \
  --profile /etc/dimos/profiles/robot.json \
  --runtime-user dimos
```

The installer writes `/etc/dimos/orin-nx.env` and three systemd units, then
runs `systemctl daemon-reload`. It never enables or starts a service.

The default sense entry is `orin-sense-headless`. It reads `DIMOS_PROFILE`
and composes only the generic ROS 2 sensor bridge and bounded headless Rerun
bridge. Use `--sense-blueprint` only when a robot needs a platform-specific
composition.

Both runtime units require the NVMe health gate. They also reject profiles with
motion output enabled. A future robot-specific motion service must have its own
explicit qualification and enablement path; it must not be added to these
sense/shadow units.

For an offline root filesystem, pass `--root <path> --no-systemctl`. Re-running
the installer with identical arguments is idempotent.
