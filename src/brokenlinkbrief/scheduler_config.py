"""Scheduler configuration validation for broken-link-brief."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brokenlinkbrief.scheduler import parse_cron_expression, validate_timezone


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
    name = config.get("name")
    if not name or not isinstance(name, str):
        raise ValueError("Project config 'name' is required")
    if not name.strip():
        raise ValueError("Project config 'name' must be non-empty")
    if len(name) > 100:
        raise ValueError("Project config 'name' must be 100 characters or fewer")

    urls = tuple(config.get("urls", []))
    _validate_urls(urls)

    # Validate schedule
    sched_raw = config.get("schedule", {})
    if not sched_raw:
        raise ValueError("Project config 'schedule' is required")
    cron_expr = sched_raw.get("cron", "0 9 * * *")
    tz = sched_raw.get("timezone", "UTC")
    try:
        parse_cron_expression(cron_expr)
    except ValueError as e:
        raise ValueError(f"Project config 'schedule.cron' is invalid: {e}")
    if not validate_timezone(tz):
        raise ValueError(f"Project config 'schedule.timezone' is invalid: {tz}")
    schedule = ScheduleConfig(cron=cron_expr, timezone=tz)

    # Validate options
    opt_raw = config.get("options", {})
    options = ProjectOptions(
        timeout=float(opt_raw.get("timeout", 10.0)),
        max_workers=int(opt_raw.get("max_workers", 3)),
    )

    # Validate notifications
    notifications = tuple(_build_notification(n) for n in config.get("notifications", []))

    return ProjectConfig(name=name, urls=urls, schedule=schedule, notifications=notifications, options=options)


def _validate_urls(urls: tuple[Any, ...]) -> None:
    """Validate the urls field of a project config."""
    if not urls:
        raise ValueError("Project config 'urls' is required with at least one URL")
    if len(urls) > 50:
        raise ValueError("Project config 'urls' must have 50 or fewer entries")
    for url in urls:
        if not isinstance(url, str):
            raise ValueError("project config 'urls' must be strings")
        # Validate URL format (must have scheme and host)
        if "://" not in url:
            raise ValueError("project config 'urls' invalid: missing scheme")
        scheme, rest = url.split("://", 1)
        if scheme not in ("http", "https"):
            raise ValueError("project config 'urls' must use http or https scheme")
        if not rest or not rest.strip("/"):
            raise ValueError("project config 'urls' invalid: missing host")


def _build_notification(n: Any) -> NotificationConfig:
    """Validate a raw notification dict and return a NotificationConfig."""
    if not isinstance(n, dict):
        raise ValueError("notification config must be a dictionary")
    n_type = n.get("type")
    if not n_type:
        raise ValueError("notification config 'type' is required")
    if n_type not in ("email", "slack", "webhook"):
        raise ValueError("notification config 'type' must be one of: email, slack, webhook")
    if n_type == "webhook" and not n.get("webhook_url"):
        raise ValueError("webhook notification config requires 'webhook_url'")
    return NotificationConfig(
        type=n.get("type", "webhook"),
        target=n.get("target", ""),
        webhook_url=n.get("webhook_url"),
    )


def load_projects_config(path: Path) -> list[ProjectConfig]:
    """Load and validate projects from a YAML or JSON config file.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the config is invalid.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    content = p.read_text(encoding="utf-8")
    if p.suffix in (".yml", ".yaml"):
        try:
            import yaml
            data = yaml.safe_load(content)
        except ImportError:
            # Fallback: try JSON parsing (YAML is superset of JSON)
            data = json.loads(content)
    else:
        data = json.loads(content)

    if not isinstance(data, dict):
        raise ValueError("Config file must contain a dictionary with 'version' and 'projects'")

    version = data.get("version")
    if version is None:
        raise ValueError("Config 'version' is required")
    if version != "1.0":
        raise ValueError(f"Config 'version' {version!r} is unsupported; only '1.0' is supported")

    projects_raw = data.get("projects")
    if not isinstance(projects_raw, list):
        raise ValueError("Config 'projects' must be a list")

    return [validate_project_config(item) for item in projects_raw]
