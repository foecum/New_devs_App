import unittest
from datetime import datetime
from importlib.util import find_spec
from types import SimpleNamespace

from app.core.tenant_resolver import TenantResolver
from app.services.reservations import calculate_monthly_revenue


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeSession:
    def __init__(self):
        self.calls = []

    async def execute(self, query, parameters):
        self.calls.append(parameters)
        if len(self.calls) == 1:
            return FakeResult([SimpleNamespace(timezone="Europe/Paris")])
        return FakeResult([
            SimpleNamespace(
                currency="USD",
                total_revenue="2250.005",
                reservation_count=4,
            )
        ])


class RevenueDashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_claimed_tenant_is_rejected_when_membership_conflicts(self):
        tenant_id = await TenantResolver.resolve_tenant_id(
            user_id="user-1",
            user_email="user@example.com",
            claimed_tenant_id="tenant-a",
            tenant_ids=["tenant-b"],
        )
        self.assertIsNone(tenant_id)

    async def test_unknown_user_does_not_get_default_tenant(self):
        tenant_id = await TenantResolver.resolve_tenant_id(
            user_id="user-1",
            user_email="unknown@example.com",
        )
        self.assertIsNone(tenant_id)

    @unittest.skipUnless(find_spec("sqlalchemy"), "SQLAlchemy is not installed")
    async def test_month_uses_property_timezone_and_rounds_to_two_decimals(self):
        session = FakeSession()

        result = await calculate_monthly_revenue(
            property_id="prop-001",
            tenant_id="tenant-a",
            month=3,
            year=2024,
            db_session=session,
        )

        self.assertEqual(result["total"], "2250.01")
        self.assertEqual(result["count"], 4)
        self.assertEqual(
            session.calls[1]["start_date"],
            datetime(2024, 3, 1, 0, 0, tzinfo=session.calls[1]["start_date"].tzinfo),
        )
        self.assertEqual(session.calls[1]["start_date"].isoformat(), "2024-02-29T23:00:00+00:00")
        self.assertEqual(session.calls[1]["end_date"].isoformat(), "2024-03-31T22:00:00+00:00")


if __name__ == "__main__":
    unittest.main()