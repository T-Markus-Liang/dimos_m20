"""Validate a robot profile and keep generic Orin services read-only."""

from __future__ import annotations

import argparse
from pathlib import Path

from dimos.hardware.platforms.profile import PlatformProfile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--allow-motion", action="store_true")
    args = parser.parse_args(argv)

    profile = PlatformProfile.from_json(args.profile)
    if profile.control.enabled and not args.allow_motion:
        print("profile rejected: motion output is enabled")
        return 1
    print(
        f"profile accepted: platform={profile.platform} "
        f"motion={'enabled' if profile.control.enabled else 'disabled'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
