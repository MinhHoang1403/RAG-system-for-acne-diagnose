from __future__ import annotations

from src.database.neo4j_queries import extract_neo4j_notifications, is_critical_neo4j_notification


class _FakeMissingPropertyNotification:
    gql_status = "01N52"
    status_description = "warn: property key does not exist. The property `name` does not exist."
    raw_severity = "WARNING"
    raw_classification = "UNRECOGNIZED"


class _FakeDeprecationNotification:
    code = "Neo.ClientNotification.Statement.FeatureDeprecationWarning"
    description = "This feature is deprecated."
    severity = "WARNING"
    classification = "DEPRECATION"


class _FakeSummary:
    def __init__(self, items):
        self.gql_status_objects = items


def test_missing_property_notification_is_critical() -> None:
    notifications = extract_neo4j_notifications(_FakeSummary([_FakeMissingPropertyNotification()]))

    assert len(notifications) == 1
    assert notifications[0]["critical"] is True
    assert is_critical_neo4j_notification(notifications[0]) is True


def test_deprecation_notification_is_reported_but_not_schema_critical() -> None:
    notifications = extract_neo4j_notifications(_FakeSummary([_FakeDeprecationNotification()]))

    assert len(notifications) == 1
    assert "critical" not in notifications[0]
    assert is_critical_neo4j_notification(notifications[0]) is False


def test_empty_summary_has_no_notifications() -> None:
    assert extract_neo4j_notifications(_FakeSummary([])) == []

