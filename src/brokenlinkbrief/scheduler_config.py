"""Scheduler configuration validation for broken-link-brief."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NotificationConfig:
    """A single notification channel configuration."""
    type: str  # email | slack | webhook
    target: str  # email addr, channel name, or URL
    webhook_url: str | None = None


@dataclass(frozen=True)
class ScheduleConfig:
    """Schedule timing configuration."""
    cron: str
    timezone: str


@dataclass(frozen=True)
class ProjectOptions:
    """Optional project scan settings."""
    timeout: float = 10.0
    max_workers: int = 3


@dataclass(frozen=True)
class ProjectConfig:
    """A validated project configuration."""
    name: str
    urls: tuple[str, ...] = ()
    schedule: ScheduleConfig = field(default_factory=lambda: ScheduleConfig(cron="0 9 * * *", timezone="UTC"))
    notifications: tuple[NotificationConfig, ...] = ()
    options: ProjectOptions = field(default_factory=ProjectOptions)


def validate_project_config(config: dict[str, Any]) -> ProjectConfig:
    """Validate a raw project config dict and return a ProjectConfig.

    Raises:
        ValueError: if any required field is missing or invalid.
    """
    # --- name ---
    name = config.get("name")
    if name is None:
        raise ValueError("name is required")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be non-empty")
    if len(name) > 100:
        raise ValueError("name must be at most 100 characters")

    # --- urls ---
    urls_raw = config.get("urls")
    if urls_raw is None:
        raise ValueError("urls is required")
    if not isinstance(urls_raw, list) or len(urls_raw) == 0:
        raise ValueError("urls must contain at least one URL")
    if len(urls_raw) > 50:
        raise ValueError("urls must contain at most 50 URLs")
    for u in urls_raw:
        if not isinstance(u, str):
            raise ValueError(f"urls entry is not a string: {u!r}")
        if not u.startswith(("http://", "https://")):
            raise ValueError(f"urls entry is invalid (must use http(s) scheme): {u}")

    # --- schedule ---
    schedule_raw = config.get("schedule")
    if schedule_raw is None:
        raise ValueError("schedule is required")
    if not isinstance(schedule_raw, dict):
        raise ValueError("schedule must be a mapping")

    cron_str = schedule_raw.get("cron")
    if not cron_str:
        raise ValueError("schedule.cron is required")
    # Validate cron expression: check field count first, then parse
    cron_fields_list = cron_str.strip().split()
    if len(cron_fields_list) != 5:
        raise ValueError(
            "cron expression is invalid: must have exactly"
            f" 5 fields, got {len(cron_fields_list)}"
        )
    from brokenlinkbrief.scheduler import parse_cron_expression, validate_timezone

    try:
        parse_cron_expression(cron_str)
    except ValueError:
        # Re-raise with a message matching "cron.*invalid"
        raise ValueError(f"cron expression is invalid: {cron_str!r}") from None

    tz = schedule_raw.get("timezone")
    if not tz:
        raise ValueError("schedule.timezone is required")
    if not validate_timezone(tz):
        raise ValueError(f"schedule.timezone is invalid: {tz}")

    sched = ScheduleConfig(cron=cron_str, timezone=tz)

    # --- notifications (optional) ---
    notifs_raw = config.get("notifications", [])
    valid_types = {"email", "slack", "webhook"}
    notif_configs: list[NotificationConfig] = []
    for nc in notifs_raw:
        if not isinstance(nc, dict):
            raise ValueError("notification entry must be a mapping")
        nc_type = nc.get("type")
        if not nc_type:
            raise ValueError("notification entry must have a 'type' field")
        if nc_type not in valid_types:
            valid_str = ", ".join(sorted(valid_types))
            raise ValueError(
                f"notification type must be one of {valid_str},"
                f" got {nc_type!r}"
            )
        target = nc.get("target", "")
        webhook_url = nc.get("webhook_url")
        if nc_type == "webhook" and not webhook_url:
            raise ValueError(
                "webhook notification must include 'webhook_url'"
            )
        notif_configs.append(
            NotificationConfig(type=nc_type, target=target, webhook_url=webhook_url)
        )

    # --- options (optional) ---
    opts_raw = config.get("options", {})
    if not isinstance(opts_raw, dict):
        raise ValueError("options must be a mapping")
    opts = ProjectOptions(
        timeout=opts_raw.get("timeout", 10.0),
        max_workers=opts_raw.get("max_workers", 3),
    )

    urls = tuple(urls_raw)
    return ProjectConfig(
        name=name.strip(),
        urls=urls,
        schedule=sched,
        notifications=tuple(notif_configs),
        options=opts,
    )


def load_projects_config(path: Path) -> list[ProjectConfig]:
    """Load and validate projects from a YAML or JSON config file.

    The file must contain a top-level mapping with:
      - version: "1.0" (required)
      - projects: list of project configs (each validated by validate_project_config)

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the config is invalid.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    text = p.read_text()
    if not text.strip():
        raise ValueError("Config file is empty")

    # Parse as JSON or YAML
    if p.suffix == ".json":
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON config: {exc}") from exc
    else:
        try:
            import yaml

            raw = yaml.safe_load(text)
        except Exception as exc:
            raise ValueError(f"Invalid YAML config: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("Config must be a YAML/JSON mapping")

    # version check
    version = raw.get("version")
    if version is None:
        raise ValueError("version is required")
    if version != "1.0":
        raise ValueError(f"version is unsupported: {version}")

    projects_raw = raw.get("projects", [])
    if not isinstance(projects_raw, list):
        raise ValueError("projects must be a list")

    results: list[ProjectConfig] = []
    for item in projects_raw:
        results.append(validate_project_config(item))
    return results
