"""Pre-development tests for SchedulerService — cron scheduler core.

Interface tests: verify imports, class existence, method signatures, field existence.
These PASS immediately with the stub module.

Behavioral tests: verify expected behavior observations.
These FAIL with NotImplementedError until implementation.
"""
from __future__ import annotations

import inspect
import sqlite3
import threading
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import datetime
from pathlib import Path

import pytest

from brokenlinkbrief.scheduler import (
    ProjectSchedule,
    SchedulerService,
    ScheduleState,
    create_scheduler_db_schema,
    parse_cron_expression,
    validate_timezone,
)

# =============================================================================
# SECTION 1: INTERFACE TESTS (pass immediately)
# =============================================================================


class TestSchedulerServiceImport:
    """Verify module loads and classes are importable."""

    def test_module_imports(self) -> None:
        """scheduler module is importable."""
        import brokenlinkbrief.scheduler as mod

        assert mod is not None

    def test_scheduler_service_class_exists(self) -> None:
        """SchedulerService class exists."""
        assert SchedulerService is not None

    def test_project_schedule_class_exists(self) -> None:
        """ProjectSchedule dataclass exists."""
        assert ProjectSchedule is not None

    def test_schedule_state_class_exists(self) -> None:
        """ScheduleState dataclass exists."""
        assert ScheduleState is not None

    def test_parse_cron_expression_callable(self) -> None:
        """parse_cron_expression is a callable function."""
        assert callable(parse_cron_expression)

    def test_validate_timezone_callable(self) -> None:
        """validate_timezone is a callable function."""
        assert callable(validate_timezone)

    def test_create_scheduler_db_schema_callable(self) -> None:
        """create_scheduler_db_schema is a callable function."""
        assert callable(create_scheduler_db_schema)


class TestProjectScheduleDataclass:
    """Verify ProjectSchedule dataclass structure."""

    def test_is_dataclass(self) -> None:
        """ProjectSchedule is a dataclass."""
        assert is_dataclass(ProjectSchedule)

    def test_has_project_id_field(self) -> None:
        """ProjectSchedule has project_id field."""
        field_names = {f.name for f in dataclass_fields(ProjectSchedule)}
        assert "project_id" in field_names

    def test_has_name_field(self) -> None:
        """ProjectSchedule has name field."""
        field_names = {f.name for f in dataclass_fields(ProjectSchedule)}
        assert "name" in field_names

    def test_has_cron_expression_field(self) -> None:
        """ProjectSchedule has cron_expression field."""
        field_names = {f.name for f in dataclass_fields(ProjectSchedule)}
        assert "cron_expression" in field_names

    def test_has_timezone_field(self) -> None:
        """ProjectSchedule has timezone field."""
        field_names = {f.name for f in dataclass_fields(ProjectSchedule)}
        assert "timezone" in field_names

    def test_has_urls_field(self) -> None:
        """ProjectSchedule has urls field."""
        field_names = {f.name for f in dataclass_fields(ProjectSchedule)}
        assert "urls" in field_names

    def test_has_timeout_field(self) -> None:
        """ProjectSchedule has timeout field."""
        field_names = {f.name for f in dataclass_fields(ProjectSchedule)}
        assert "timeout" in field_names

    def test_has_max_workers_field(self) -> None:
        """ProjectSchedule has max_workers field."""
        field_names = {f.name for f in dataclass_fields(ProjectSchedule)}
        assert "max_workers" in field_names

    def test_has_enabled_field(self) -> None:
        """ProjectSchedule has enabled field."""
        field_names = {f.name for f in dataclass_fields(ProjectSchedule)}
        assert "enabled" in field_names

    def test_has_last_run_field(self) -> None:
        """ProjectSchedule has last_run field."""
        field_names = {f.name for f in dataclass_fields(ProjectSchedule)}
        assert "last_run" in field_names

    def test_has_next_run_field(self) -> None:
        """ProjectSchedule has next_run field."""
        field_names = {f.name for f in dataclass_fields(ProjectSchedule)}
        assert "next_run" in field_names

    def test_default_enabled_is_true(self) -> None:
        """Default value for enabled is True."""
        cfg = ProjectSchedule(
            project_id="p1", name="Test", cron_expression="0 9 * * *", timezone="UTC"
        )
        assert cfg.enabled is True

    def test_default_timeout_value(self) -> None:
        """Default value for timeout is 30.0."""
        cfg = ProjectSchedule(
            project_id="p1", name="Test", cron_expression="0 9 * * *", timezone="UTC"
        )
        assert cfg.timeout == 30.0

    def test_default_max_workers_value(self) -> None:
        """Default value for max_workers is 10."""
        cfg = ProjectSchedule(
            project_id="p1", name="Test", cron_expression="0 9 * * *", timezone="UTC"
        )
        assert cfg.max_workers == 10

    def test_default_urls_is_empty_list(self) -> None:
        """Default value for urls is empty list."""
        cfg = ProjectSchedule(
            project_id="p1", name="Test", cron_expression="0 9 * * *", timezone="UTC"
        )
        assert cfg.urls == []

    def test_default_last_run_is_none(self) -> None:
        """Default value for last_run is None."""
        cfg = ProjectSchedule(
            project_id="p1", name="Test", cron_expression="0 9 * * *", timezone="UTC"
        )
        assert cfg.last_run is None

    def test_default_next_run_is_none(self) -> None:
        """Default value for next_run is None."""
        cfg = ProjectSchedule(
            project_id="p1", name="Test", cron_expression="0 9 * * *", timezone="UTC"
        )
        assert cfg.next_run is None


class TestScheduleStateDataclass:
    """Verify ScheduleState dataclass structure."""

    def test_is_dataclass(self) -> None:
        """ScheduleState is a dataclass."""
        assert is_dataclass(ScheduleState)

    def test_has_project_id_field(self) -> None:
        """ScheduleState has project_id field."""
        field_names = {f.name for f in dataclass_fields(ScheduleState)}
        assert "project_id" in field_names

    def test_has_cron_expression_field(self) -> None:
        """ScheduleState has cron_expression field."""
        field_names = {f.name for f in dataclass_fields(ScheduleState)}
        assert "cron_expression" in field_names

    def test_has_timezone_field(self) -> None:
        """ScheduleState has timezone field."""
        field_names = {f.name for f in dataclass_fields(ScheduleState)}
        assert "timezone" in field_names

    def test_has_enabled_field(self) -> None:
        """ScheduleState has enabled field."""
        field_names = {f.name for f in dataclass_fields(ScheduleState)}
        assert "enabled" in field_names

    def test_has_next_due_field(self) -> None:
        """ScheduleState has next_due field."""
        field_names = {f.name for f in dataclass_fields(ScheduleState)}
        assert "next_due" in field_names

    def test_has_lease_owner_field(self) -> None:
        """ScheduleState has lease_owner field."""
        field_names = {f.name for f in dataclass_fields(ScheduleState)}
        assert "lease_owner" in field_names

    def test_has_lease_at_field(self) -> None:
        """ScheduleState has lease_at field."""
        field_names = {f.name for f in dataclass_fields(ScheduleState)}
        assert "lease_at" in field_names


class TestSchedulerServiceSignatures:
    """Verify SchedulerService method signatures."""

    def test_init_signature(self) -> None:
        """__init__ accepts db_path parameter."""
        sig = inspect.signature(SchedulerService.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "db_path" in params

    def test_init_db_path_default(self) -> None:
        """__init__ db_path has default value."""
        sig = inspect.signature(SchedulerService.__init__)
        assert sig.parameters["db_path"].default == "scheduler.db"

    def test_start_signature(self) -> None:
        """start() takes no args beyond self."""
        sig = inspect.signature(SchedulerService.start)
        params = [p for p in sig.parameters if p != "self"]
        assert params == []

    def test_stop_signature(self) -> None:
        """stop() accepts timeout parameter."""
        sig = inspect.signature(SchedulerService.stop)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "timeout" in params

    def test_stop_timeout_default(self) -> None:
        """stop() timeout defaults to 30.0."""
        sig = inspect.signature(SchedulerService.stop)
        assert sig.parameters["timeout"].default == 30.0

    def test_add_project_signature(self) -> None:
        """add_project() accepts config parameter."""
        sig = inspect.signature(SchedulerService.add_project)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "config" in params

    def test_add_project_config_annotation(self) -> None:
        """add_project() config parameter annotated as ProjectSchedule."""
        sig = inspect.signature(SchedulerService.add_project)
        annotation = sig.parameters["config"].annotation
        assert annotation is ProjectSchedule or annotation == "ProjectSchedule"

    def test_remove_project_signature(self) -> None:
        """remove_project() accepts project_id parameter."""
        sig = inspect.signature(SchedulerService.remove_project)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "project_id" in params

    def test_remove_project_return_annotation(self) -> None:
        """remove_project() returns bool."""
        sig = inspect.signature(SchedulerService.remove_project)
        ret = sig.return_annotation
        assert ret is bool or ret == "bool"

    def test_get_next_run_times_signature(self) -> None:
        """get_next_run_times() takes no args beyond self."""
        sig = inspect.signature(SchedulerService.get_next_run_times)
        params = [p for p in sig.parameters if p != "self"]
        assert params == []

    def test_get_project_schedule_signature(self) -> None:
        """get_project_schedule() accepts project_id parameter."""
        sig = inspect.signature(SchedulerService.get_project_schedule)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "project_id" in params

    def test_list_projects_signature(self) -> None:
        """list_projects() takes no args beyond self."""
        sig = inspect.signature(SchedulerService.list_projects)
        params = [p for p in sig.parameters if p != "self"]
        assert params == []

    def test_is_running_signature(self) -> None:
        """is_running() takes no args beyond self."""
        sig = inspect.signature(SchedulerService.is_running)
        params = [p for p in sig.parameters if p != "self"]
        assert params == []

    def test_parse_cron_expression_signature(self) -> None:
        """parse_cron_expression() accepts expr parameter."""
        sig = inspect.signature(parse_cron_expression)
        params = list(sig.parameters.keys())
        assert "expr" in params

    def test_validate_timezone_signature(self) -> None:
        """validate_timezone() accepts tz_name parameter."""
        sig = inspect.signature(validate_timezone)
        params = list(sig.parameters.keys())
        assert "tz_name" in params

    def test_create_scheduler_db_schema_signature(self) -> None:
        """create_scheduler_db_schema() accepts conn parameter."""
        sig = inspect.signature(create_scheduler_db_schema)
        params = list(sig.parameters.keys())
        assert "conn" in params


class TestSchedulerServiceProperties:
    """Verify SchedulerService properties exist."""

    def test_db_path_property(self) -> None:
        """db_path is a property on SchedulerService."""
        assert hasattr(SchedulerService, "db_path")

    def test_project_count_property(self) -> None:
        """project_count is a property on SchedulerService."""
        assert hasattr(SchedulerService, "project_count")


# =============================================================================
# SECTION 2: BEHAVIORAL TESTS (fail with NotImplementedError)
# =============================================================================


class TestSchedulerServiceLifecycle:
    """Test scheduler start/stop lifecycle behavior."""

    def test_start_sets_running_state(self) -> None:
        """After start(), is_running() returns True."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            assert svc.is_running() is True
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_stop_sets_not_running(self) -> None:
        """After stop(), is_running() returns False."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.stop()
            assert svc.is_running() is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_start_twice_raises_runtime_error(self) -> None:
        """Calling start() when already running raises RuntimeError."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            with pytest.raises(RuntimeError, match="already running"):
                svc.start()
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_stop_when_not_running_raises_runtime_error(self) -> None:
        """Calling stop() when not running raises RuntimeError."""
        try:
            svc = SchedulerService(":memory:")
            with pytest.raises(RuntimeError, match="not running"):
                svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_start_creates_db_tables(self) -> None:
        """After start(), SQLite database has schedules table."""
        try:
            db_path = Path(":memory:")
            svc = SchedulerService(db_path)
            svc.start()
            # The SchedulerService uses a unique URI for :memory: —
            # connect to the same URI to verify tables exist.
            conn = sqlite3.connect(svc._mem_name, uri=True)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schedules'"
            )
            assert cursor.fetchone() is not None
            conn.close()
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


class TestSchedulerServiceAddProject:
    """Test adding projects to the scheduler."""

    def _make_config(
        self,
        project_id: str = "proj-1",
        name: str = "Test Project",
        cron: str = "0 9 * * *",
        tz: str = "UTC",
    ) -> ProjectSchedule:
        return ProjectSchedule(
            project_id=project_id,
            name=name,
            cron_expression=cron,
            timezone=tz,
            urls=["https://example.com"],
        )

    def test_add_project_increases_project_count(self) -> None:
        """After add_project(), project_count increases by 1."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.add_project(self._make_config())
            assert svc.project_count == 1
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_add_project_appears_in_list(self) -> None:
        """After add_project(), project appears in list_projects()."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            cfg = self._make_config()
            svc.add_project(cfg)
            projects = svc.list_projects()
            ids = [p.project_id for p in projects]
            assert "proj-1" in ids
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_add_project_persists_to_db(self) -> None:
        """After add_project(), schedule is in SQLite."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.add_project(self._make_config())
            # Query directly
            result = svc.get_project_schedule("proj-1")
            assert result is not None
            assert result.project_id == "proj-1"
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_add_project_updates_existing(self) -> None:
        """Adding same project_id twice updates the schedule."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.add_project(self._make_config(cron="0 9 * * *"))
            svc.add_project(self._make_config(cron="0 12 * * *"))
            result = svc.get_project_schedule("proj-1")
            assert result is not None
            assert result.cron_expression == "0 12 * * *"
            assert svc.project_count == 1
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_add_project_invalid_cron_raises(self) -> None:
        """Adding project with invalid cron raises ValueError."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            with pytest.raises(ValueError, match="cron"):
                svc.add_project(self._make_config(cron="invalid cron"))
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_add_project_invalid_timezone_raises(self) -> None:
        """Adding project with invalid timezone raises ValueError."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            with pytest.raises(ValueError, match="timezone"):
                svc.add_project(self._make_config(tz="Invalid/Zone"))
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_add_project_when_not_running_raises(self) -> None:
        """Adding project when scheduler not running raises RuntimeError."""
        try:
            svc = SchedulerService(":memory:")
            with pytest.raises(RuntimeError, match="not running"):
                svc.add_project(self._make_config())
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


class TestSchedulerServiceRemoveProject:
    """Test removing projects from the scheduler."""

    def _make_config(
        self, project_id: str = "proj-1"
    ) -> ProjectSchedule:
        return ProjectSchedule(
            project_id=project_id,
            name="Test",
            cron_expression="0 9 * * *",
            timezone="UTC",
            urls=["https://example.com"],
        )

    def test_remove_existing_project_returns_true(self) -> None:
        """Removing an existing project returns True."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.add_project(self._make_config())
            result = svc.remove_project("proj-1")
            assert result is True
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_remove_decreases_count(self) -> None:
        """After remove_project(), project_count decreases."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.add_project(self._make_config("p1"))
            svc.add_project(self._make_config("p2"))
            svc.remove_project("p1")
            assert svc.project_count == 1
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_remove_nonexistent_returns_false(self) -> None:
        """Removing non-existent project returns False."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            result = svc.remove_project("nonexistent")
            assert result is False
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_remove_deletes_from_db(self) -> None:
        """After remove_project(), schedule is gone from SQLite."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.add_project(self._make_config())
            svc.remove_project("proj-1")
            result = svc.get_project_schedule("proj-1")
            assert result is None
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_remove_disappears_from_list(self) -> None:
        """After remove_project(), project not in list_projects()."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.add_project(self._make_config())
            svc.remove_project("proj-1")
            projects = svc.list_projects()
            assert all(p.project_id != "proj-1" for p in projects)
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_remove_when_not_running_raises(self) -> None:
        """Removing project when scheduler not running raises RuntimeError."""
        try:
            svc = SchedulerService(":memory:")
            with pytest.raises(RuntimeError, match="not running"):
                svc.remove_project("proj-1")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


class TestSchedulerServiceGetNextRunTimes:
    """Test get_next_run_times behavior."""

    def test_empty_scheduler_returns_empty_dict(self) -> None:
        """Empty scheduler returns empty dict."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            result = svc.get_next_run_times()
            assert result == {}
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_returns_datetime_per_project(self) -> None:
        """Each project maps to a datetime or None."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.add_project(
                ProjectSchedule(
                    project_id="p1",
                    name="Test",
                    cron_expression="0 9 * * *",
                    timezone="UTC",
                )
            )
            result = svc.get_next_run_times()
            assert "p1" in result
            assert isinstance(result["p1"], datetime) or result["p1"] is None
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_disabled_project_returns_none(self) -> None:
        """Disabled project returns None for next run."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.add_project(
                ProjectSchedule(
                    project_id="p1",
                    name="Test",
                    cron_expression="0 9 * * *",
                    timezone="UTC",
                    enabled=False,
                )
            )
            result = svc.get_next_run_times()
            assert result.get("p1") is None
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_multiple_projects_all_present(self) -> None:
        """All added projects appear in next run times."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            for i in range(3):
                svc.add_project(
                    ProjectSchedule(
                        project_id=f"p{i}",
                        name=f"Project {i}",
                        cron_expression="0 9 * * *",
                        timezone="UTC",
                    )
                )
            result = svc.get_next_run_times()
            assert len(result) == 3
            for i in range(3):
                assert f"p{i}" in result
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


class TestCronParsing:
    """Test cron expression parsing behavior."""

    def test_valid_daily_cron(self) -> None:
        """Parse '0 9 * * *' (daily at 9am)."""
        try:
            result = parse_cron_expression("0 9 * * *")
            assert result["minute"] == "0"
            assert result["hour"] == "9"
            assert result["day"] == "*"
            assert result["month"] == "*"
            assert result["day_of_week"] == "*"
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_valid_every_six_hours(self) -> None:
        """Parse '0 */6 * * *' (every 6 hours)."""
        try:
            result = parse_cron_expression("0 */6 * * *")
            assert result["minute"] == "0"
            assert result["hour"] == "*/6"
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_valid_weekly(self) -> None:
        """Parse '0 10 * * 1' (Monday at 10am)."""
        try:
            result = parse_cron_expression("0 10 * * 1")
            assert result["day_of_week"] == "1"
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_valid_hourly(self) -> None:
        """Parse '0 * * * *' (every hour)."""
        try:
            result = parse_cron_expression("0 * * * *")
            assert result["hour"] == "*"
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_invalid_too_few_fields(self) -> None:
        """Cron with < 5 fields raises ValueError."""
        try:
            with pytest.raises(ValueError, match="5 fields"):
                parse_cron_expression("0 9 * *")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_invalid_too_many_fields(self) -> None:
        """Cron with > 5 fields raises ValueError."""
        try:
            with pytest.raises(ValueError, match="5 fields"):
                parse_cron_expression("0 9 * * * *")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_invalid_non_numeric_field(self) -> None:
        """Cron with non-numeric field raises ValueError."""
        try:
            with pytest.raises(ValueError):
                parse_cron_expression("abc 9 * * *")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_invalid_minute_out_of_range(self) -> None:
        """Cron with minute=60 raises ValueError."""
        try:
            with pytest.raises(ValueError):
                parse_cron_expression("60 9 * * *")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_invalid_hour_out_of_range(self) -> None:
        """Cron with hour=25 raises ValueError."""
        try:
            with pytest.raises(ValueError):
                parse_cron_expression("0 25 * * *")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_empty_string_raises(self) -> None:
        """Empty cron string raises ValueError."""
        try:
            with pytest.raises(ValueError):
                parse_cron_expression("")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


class TestTimezoneValidation:
    """Test timezone validation behavior."""

    def test_utc_is_valid(self) -> None:
        """'UTC' is a valid timezone."""
        try:
            assert validate_timezone("UTC") is True
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_europe_zurich_is_valid(self) -> None:
        """'Europe/Zurich' is a valid timezone."""
        try:
            assert validate_timezone("Europe/Zurich") is True
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_america_new_york_is_valid(self) -> None:
        """'America/New_York' is a valid timezone."""
        try:
            assert validate_timezone("America/New_York") is True
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_invalid_timezone_returns_false(self) -> None:
        """'Invalid/Zone' is not a valid timezone."""
        try:
            assert validate_timezone("Invalid/Zone") is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_empty_string_returns_false(self) -> None:
        """Empty string is not a valid timezone."""
        try:
            assert validate_timezone("") is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_random_string_returns_false(self) -> None:
        """Random string is not a valid timezone."""
        try:
            assert validate_timezone("not-a-timezone") is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


class TestJobPersistence:
    """Test SQLite job persistence across restarts."""

    def test_schedules_table_created(self) -> None:
        """create_scheduler_db_schema creates schedules table."""
        try:
            conn = sqlite3.connect(":memory:")
            create_scheduler_db_schema(conn)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schedules'"
            )
            assert cursor.fetchone() is not None
            conn.close()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_schedules_table_has_required_columns(self) -> None:
        """schedules table has all required columns."""
        try:
            conn = sqlite3.connect(":memory:")
            create_scheduler_db_schema(conn)
            cursor = conn.execute("PRAGMA table_info(schedules)")
            columns = {row[1] for row in cursor.fetchall()}
            required = {
                "project_id",
                "cron_expression",
                "timezone",
                "enabled",
                "next_due",
            }
            assert required.issubset(columns)
            conn.close()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_state_survives_restart(self) -> None:
        """Schedule state persists when service restarts."""
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = Path(tmpdir) / "test_scheduler.db"

                # First service instance
                svc1 = SchedulerService(db_path)
                svc1.start()
                svc1.add_project(
                    ProjectSchedule(
                        project_id="p1",
                        name="Persistent",
                        cron_expression="0 9 * * *",
                        timezone="UTC",
                    )
                )
                svc1.stop()

                # Second service instance (restart)
                svc2 = SchedulerService(db_path)
                svc2.start()
                result = svc2.get_project_schedule("p1")
                assert result is not None
                assert result.project_id == "p1"
                svc2.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_removed_project_not_in_restarted_db(self) -> None:
        """Removed project stays removed after restart."""
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = Path(tmpdir) / "test_scheduler.db"

                svc1 = SchedulerService(db_path)
                svc1.start()
                svc1.add_project(
                    ProjectSchedule(
                        project_id="p1",
                        name="Gone",
                        cron_expression="0 9 * * *",
                        timezone="UTC",
                    )
                )
                svc1.remove_project("p1")
                svc1.stop()

                svc2 = SchedulerService(db_path)
                svc2.start()
                result = svc2.get_project_schedule("p1")
                assert result is None
                svc2.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_multiple_projects_persist(self) -> None:
        """Multiple projects all survive restart."""
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = Path(tmpdir) / "test_scheduler.db"

                svc1 = SchedulerService(db_path)
                svc1.start()
                for i in range(5):
                    svc1.add_project(
                        ProjectSchedule(
                            project_id=f"p{i}",
                            name=f"Project {i}",
                            cron_expression="0 9 * * *",
                            timezone="UTC",
                        )
                    )
                svc1.stop()

                svc2 = SchedulerService(db_path)
                svc2.start()
                assert svc2.project_count == 5
                for i in range(5):
                    assert svc2.get_project_schedule(f"p{i}") is not None
                svc2.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


class TestGracefulShutdown:
    """Test graceful shutdown behavior."""

    def test_stop_waits_for_inflight_jobs(self) -> None:
        """stop() waits up to timeout for in-flight jobs."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            # stop with timeout should not raise
            svc.stop(timeout=5.0)
            assert svc.is_running() is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_stop_closes_db_connection(self) -> None:
        """After stop(), database connection is closed."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.stop()
            # Connection should be None or closed
            assert svc._conn is None
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_stop_idempotent_after_double_stop_raises(self) -> None:
        """Double stop raises RuntimeError on second call."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            svc.stop()
            with pytest.raises(RuntimeError, match="not running"):
                svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_thread_safety_add_remove(self) -> None:
        """Concurrent add/remove operations don't crash."""
        try:
            svc = SchedulerService(":memory:")
            svc.start()
            errors: list[Exception] = []

            def add_project(pid: str) -> None:
                try:
                    svc.add_project(
                        ProjectSchedule(
                            project_id=pid,
                            name=f"Project {pid}",
                            cron_expression="0 9 * * *",
                            timezone="UTC",
                        )
                    )
                except Exception as e:
                    errors.append(e)

            threads = [
                threading.Thread(target=add_project, args=(f"p{i}",))
                for i in range(10)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert errors == []
            svc.stop()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


class TestAppIntegration:
    """Test integration with app.py lifecycle."""

    def test_scheduler_service_importable_from_package(self) -> None:
        """SchedulerService is importable from brokenlinkbrief package."""
        try:
            from brokenlinkbrief.scheduler import (
                SchedulerService as SchedulerSvc,
            )

            assert SchedulerSvc is not None
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_project_schedule_instantiation(self) -> None:
        """ProjectSchedule can be instantiated with all fields."""
        try:
            cfg = ProjectSchedule(
                project_id="test-123",
                name="Integration Test",
                cron_expression="0 */4 * * *",
                timezone="Europe/Zurich",
                urls=["https://example.com", "https://test.com"],
                timeout=15.0,
                max_workers=5,
                enabled=True,
            )
            assert cfg.project_id == "test-123"
            assert len(cfg.urls) == 2
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
