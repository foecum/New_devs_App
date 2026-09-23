from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict
from zoneinfo import ZoneInfo


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session=None,
) -> Dict[str, Any]:
    """
    Calculate revenue for a property-local calendar month.
    """

    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")

    if db_session is None:
        from app.core.database_pool import db_pool

        if db_pool.session_factory is None:
            await db_pool.initialize()
        if db_pool.session_factory is None:
            raise RuntimeError("Database pool is not available")
        async with db_pool.get_session() as session:
            return await calculate_monthly_revenue(
                property_id, tenant_id, month, year, session
            )

    from sqlalchemy import text

    property_result = await db_session.execute(
        text("""
            SELECT timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    property_row = property_result.fetchone()
    if property_row is None:
        raise LookupError("Property not found for tenant")

    try:
        property_timezone = ZoneInfo(property_row.timezone)
    except Exception as error:
        raise ValueError("Property has an invalid timezone") from error

    start_local = datetime(year, month, 1, tzinfo=property_timezone)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=property_timezone)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=property_timezone)

    result = await db_session.execute(
        text("""
            SELECT currency, SUM(total_amount) AS total_revenue, COUNT(*) AS reservation_count
            FROM reservations
            WHERE property_id = :property_id
              AND tenant_id = :tenant_id
              AND check_in_date >= :start_date
              AND check_in_date < :end_date
            GROUP BY currency
        """),
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_local.astimezone(ZoneInfo("UTC")),
            "end_date": end_local.astimezone(ZoneInfo("UTC")),
        },
    )
    rows = result.fetchall()
    currencies = {row.currency for row in rows}
    if len(currencies) > 1:
        raise ValueError("Cannot aggregate reservations with mixed currencies")

    total = Decimal("0").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    count = 0
    currency = next(iter(currencies), "USD")
    if rows:
        total = Decimal(str(rows[0].total_revenue)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        count = rows[0].reservation_count

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": format(total, ".2f"),
        "currency": currency,
        "count": count,
        "month": month,
        "year": year,
    }

async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        return await calculate_monthly_revenue(property_id, tenant_id, month, year)
    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        raise
