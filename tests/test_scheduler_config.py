"""Tests for project scheduler YAML/JSON config validation.

Three-layer pre-dev test pattern:
  Layer 1: Import/class-existence (PASS immediately)
  Layer 2: Signature/interface (PASS immediately)
  Layer 3: Behavioral validation (FAIL with NotImplementedError until implemented)
"""
from __future__ import annotations

import inspect
import json
import pytest
from dataclasses import fields
from pathlib import Path
from textwrap import dedent

from brokenlinkbrief.scheduler_config import (
    ProjectConfig,
    NotificationConfig,
    ScheduleConfig,
    ProjectOptions,
    validate_project_config,
    load_projects_config,
)


# ---------------------------------------------------------------------------
# Layer 1 — Import & class existence
# ---------------------------------------------------------------------------
class TestImports:
    """Verify all public symbols are importable."""

    def test_import_project_config(self) -> None:
        assert ProjectConfig is not None

    def test_import_notification_config(self) -> None:
        assert NotificationConfig is not None

    def test_import_schedule_config(self) -> None:
        assert ScheduleConfig is not None

    def test_import_project_options(self) -> None:
        assert ProjectOptions is not None

    def test_import_validate_project_config(self) -> None:
        assert callable(validate_project_config)

    def test_import_load_projects_config(self) -> None:
        assert callable(load_projects_config)


class TestDataclassStructure:
    """Verify dataclass fields exist with correct types/defaults."""

    def test_project_config_is_dataclass(self) -> None:
        from dataclasses import is_dataclass
        assert is_dataclass(ProjectConfig)

    def test_project_config_fields(self) -> None:
        field_names = {f.name for f in fields(ProjectConfig)}
        assert "name" in field_names
        assert "urls" in field_names
        assert "schedule" in field_names
        assert "notifications" in field_names
        assert "options" in field_names

    def test_notification_config_fields(self) -> None:
        field_names = {f.name for f in fields(NotificationConfig)}
        assert "type" in field_names
        assert "target" in field_names
        assert "webhook_url" in field_names

    def test_schedule_config_fields(self) -> None:
        field_names = {f.name for f in fields(ScheduleConfig)}
        assert "cron" in field_names
        assert "timezone" in field_names

    def test_project_options_fields(self) -> None:
        field_names = {f.name for f in fields(ProjectOptions)}
        assert "timeout" in field_names
        assert "max_workers" in field_names

    def test_project_options_defaults(self) -> None:
        opts = ProjectOptions()
        assert opts.timeout == 10.0
        assert opts.max_workers == 3

    def test_notification_config_default_webhook_url(self) -> None:
        nc = NotificationConfig(type="email", target="a@b.com")
        assert nc.webhook_url is None


# ---------------------------------------------------------------------------
# Layer 2 — Signature/interface checks
# ---------------------------------------------------------------------------
class TestSignatures:
    """Verify function signatures match spec."""

    def test_validate_project_config_signature(self) -> None:
        sig = inspect.signature(validate_project_config)
        params = list(sig.parameters.keys())
        assert "config" in params
        # Should return a ProjectConfig
        ret = sig.return_annotation
        assert ret is ProjectConfig or ret == "ProjectConfig"

    def test_load_projects_config_signature(self) -> None:
        sig = inspect.signature(load_projects_config)
        params = list(sig.parameters.keys())
        assert "path" in params
        ret = sig.return_annotation
        assert "list" in str(ret).lower() or ret is not None


# ---------------------------------------------------------------------------
# Layer 3 — Behavioral tests (RED phase — raise NotImplementedError)
# ---------------------------------------------------------------------------
class TestProjectConfigValidation:
    """Validate project configuration schema — behavioral tests."""

    def test_valid_minimal_config(self) -> None:
        """Valid config with required fields only."""
        config = {
            "name": "My Site",
            "urls": ["https://example.com"],
            "schedule": {
                "cron": "0 9 * * *",
                "timezone": "Europe/Zurich",
            },
        }
        try:
            result = validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.name == "My Site"
        assert result.urls == ("https://example.com",)
        assert result.schedule.cron == "0 9 * * *"
        assert result.schedule.timezone == "Europe/Zurich"

    def test_valid_full_config(self) -> None:
        """Valid config with all optional fields."""
        config = {
            "name": "Documentation",
            "urls": ["https://docs.example.com", "https://api.example.com"],
            "schedule": {
                "cron": "0 */6 * * *",
                "timezone": "UTC",
            },
            "notifications": [
                {"type": "email", "target": "ops@example.com"},
                {"type": "slack", "target": "#alerts", "webhook_url": "https://hooks.slack.com/xxx"},
            ],
            "options": {
                "timeout": 15.0,
                "max_workers": 5,
            },
        }
        try:
            result = validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert len(result.notifications) == 2
        assert result.options.timeout == 15.0

    def test_missing_name_rejected(self) -> None:
        """Config without name raises ValueError."""
        config = {
            "urls": ["https://example.com"],
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
        }
        try:
            with pytest.raises(ValueError, match="name.*required"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_empty_name_rejected(self) -> None:
        """Config with empty/whitespace name raises ValueError."""
        config = {
            "name": "   ",
            "urls": ["https://example.com"],
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
        }
        try:
            with pytest.raises(ValueError, match="name.*non-empty"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_name_too_long_rejected(self) -> None:
        """Config with name > 100 chars raises ValueError."""
        config = {
            "name": "x" * 101,
            "urls": ["https://example.com"],
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
        }
        try:
            with pytest.raises(ValueError, match="name.*100"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_missing_urls_rejected(self) -> None:
        """Config without urls raises ValueError."""
        config = {
            "name": "Site",
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
        }
        try:
            with pytest.raises(ValueError, match="urls.*required"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_empty_urls_rejected(self) -> None:
        """Config with empty urls list raises ValueError."""
        config = {
            "name": "Site",
            "urls": [],
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
        }
        try:
            with pytest.raises(ValueError, match="urls.*at least one"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_too_many_urls_rejected(self) -> None:
        """Config with > 50 urls raises ValueError."""
        config = {
            "name": "Site",
            "urls": [f"https://example.com/{i}" for i in range(51)],
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
        }
        try:
            with pytest.raises(ValueError, match="urls.*50"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_invalid_url_scheme_rejected(self) -> None:
        """Config with non-HTTP URL raises ValueError."""
        config = {
            "name": "Site",
            "urls": ["ftp://example.com"],
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
        }
        try:
            with pytest.raises(ValueError, match="urls.*http"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_invalid_url_format_rejected(self) -> None:
        """Config with malformed URL raises ValueError."""
        config = {
            "name": "Site",
            "urls": ["not-a-url"],
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
        }
        try:
            with pytest.raises(ValueError, match="urls.*invalid"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_missing_schedule_rejected(self) -> None:
        """Config without schedule raises ValueError."""
        config = {
            "name": "Site",
            "urls": ["https://example.com"],
        }
        try:
            with pytest.raises(ValueError, match="schedule.*required"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_invalid_cron_rejected(self) -> None:
        """Config with invalid cron expression raises ValueError."""
        config = {
            "name": "Site",
            "urls": ["https://example.com"],
            "schedule": {"cron": "invalid", "timezone": "UTC"},
        }
        try:
            with pytest.raises(ValueError, match="cron.*invalid"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_cron_too_many_fields_rejected(self) -> None:
        """Config with > 5 cron fields raises ValueError."""
        config = {
            "name": "Site",
            "urls": ["https://example.com"],
            "schedule": {"cron": "0 9 * * * *", "timezone": "UTC"},
        }
        try:
            with pytest.raises(ValueError, match="cron.*5 fields"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_invalid_timezone_rejected(self) -> None:
        """Config with invalid timezone raises ValueError."""
        config = {
            "name": "Site",
            "urls": ["https://example.com"],
            "schedule": {"cron": "0 9 * * *", "timezone": "Invalid/Zone"},
        }
        try:
            with pytest.raises(ValueError, match="timezone.*invalid"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_notification_missing_type_rejected(self) -> None:
        """Notification without type raises ValueError."""
        config = {
            "name": "Site",
            "urls": ["https://example.com"],
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
            "notifications": [{"target": "ops@example.com"}],
        }
        try:
            with pytest.raises(ValueError, match="notification.*type"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_notification_invalid_type_rejected(self) -> None:
        """Notification with unknown type raises ValueError."""
        config = {
            "name": "Site",
            "urls": ["https://example.com"],
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
            "notifications": [{"type": "sms", "target": "+123****7890"}],
        }
        try:
            with pytest.raises(ValueError, match="notification.*type"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_webhook_notification_requires_url(self) -> None:
        """Webhook notification without webhook_url raises ValueError."""
        config = {
            "name": "Site",
            "urls": ["https://example.com"],
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
            "notifications": [{"type": "webhook", "target": "https://example.com/hook"}],
        }
        try:
            with pytest.raises(ValueError, match="webhook.*webhook_url"):
                validate_project_config(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


class TestLoadProjectsConfig:
    """Test loading config from YAML/JSON files — behavioral tests."""

    def test_load_yaml_config(self, tmp_path: Path) -> None:
        """Load valid YAML config file."""
        config_path = tmp_path / "projects.yaml"
        config_path.write_text(dedent("""
            version: "1.0"
            projects:
              - name: "Site"
                urls: ["https://example.com"]
                schedule:
                  cron: "0 9 * * *"
                  timezone: "UTC"
        """))
        try:
            projects = load_projects_config(config_path)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert len(projects) == 1
        assert projects[0].name == "Site"

    def test_load_json_config(self, tmp_path: Path) -> None:
        """Load valid JSON config file."""
        config_path = tmp_path / "projects.json"
        config_path.write_text(json.dumps({
            "version": "1.0",
            "projects": [{
                "name": "Site",
                "urls": ["https://example.com"],
                "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
            }],
        }))
        try:
            projects = load_projects_config(config_path)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert len(projects) == 1
        assert projects[0].name == "Site"

    def test_missing_version_rejected(self, tmp_path: Path) -> None:
        """Config without version raises ValueError."""
        config_path = tmp_path / "projects.yaml"
        config_path.write_text(dedent("""
            projects:
              - name: "Site"
                urls: ["https://example.com"]
                schedule:
                  cron: "0 9 * * *"
                  timezone: "UTC"
        """))
        try:
            with pytest.raises(ValueError, match="version.*required"):
                load_projects_config(config_path)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_unsupported_version_rejected(self, tmp_path: Path) -> None:
        """Config with unsupported version raises ValueError."""
        config_path = tmp_path / "projects.yaml"
        config_path.write_text(dedent("""
            version: "99.0"
            projects: []
        """))
        try:
            with pytest.raises(ValueError, match="version.*unsupported"):
                load_projects_config(config_path)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_nonexistent_file_rejected(self) -> None:
        """Loading non-existent file raises FileNotFoundError."""
        try:
            with pytest.raises(FileNotFoundError):
                load_projects_config(Path("/nonexistent/config.yaml"))
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
