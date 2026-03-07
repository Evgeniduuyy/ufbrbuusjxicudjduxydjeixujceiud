from datetime import date, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.models.subscription import Subscription
from app.config import Config

async def check_and_reset_daily_limits(user: User, session: AsyncSession):
    today = date.today()
    if user.last_reset_date != today:
        user.free_solves_today = 0
        user.free_autos_today = 0
        user.last_reset_date = today
        await session.commit()

async def has_active_subscription(user_id: int, session: AsyncSession) -> bool:
    stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.end_date > datetime.utcnow()
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None

async def can_use_solve(user: User, session: AsyncSession) -> bool:
    if await has_active_subscription(user.id, session):
        return True
    return user.free_solves_today < Config.MAX_FREE_SOLVES

async def can_use_auto(user: User, session: AsyncSession) -> bool:
    if await has_active_subscription(user.id, session):
        return True
    return user.free_autos_today < Config.MAX_FREE_AUTOS

async def increment_solve_usage(user: User, session: AsyncSession):
    if not await has_active_subscription(user.id, session):
        user.free_solves_today += 1
        await session.commit()

async def increment_auto_usage(user: User, session: AsyncSession):
    if not await has_active_subscription(user.id, session):
        user.free_autos_today += 1
        await session.commit()

async def add_subscription_days(user_id: int, days: int, session: AsyncSession):
    now = datetime.utcnow()
    new_end = now + timedelta(days=days)
    stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.end_date > now
    ).order_by(Subscription.end_date.desc())
    result = await session.execute(stmt)
    active = result.scalar_one_or_none()
    if active:
        active.end_date += timedelta(days=days)
    else:
        session.add(Subscription(user_id=user_id, start_date=now, end_date=new_end))
    await session.commit()
