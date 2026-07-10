from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def _make_engines(database_url: str, database_sync_url: str):
    async_eng = create_async_engine(database_url, pool_pre_ping=True)
    sync_eng = create_engine(database_sync_url, pool_pre_ping=True)
    return async_eng, sync_eng


from app.core.config import settings

async_engine, sync_engine = _make_engines(settings.database_url, settings.database_sync_url)

AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

SyncSessionLocal = sessionmaker(bind=sync_engine)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
