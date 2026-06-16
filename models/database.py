from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, event
from config import settings

# Pour SQLite : un seul thread à la fois via NullPool
if "sqlite" in settings.DATABASE_URL:
    from sqlalchemy.pool import StaticPool
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        connect_args={
            "check_same_thread": False,
            "timeout": 60,
        },
        poolclass=StaticPool,  # connexion unique partagée → évite database is locked
    )
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,   # évite les flushes implicites inattendus
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    async with engine.begin() as conn:
        if "sqlite" in settings.DATABASE_URL:
            # WAL mode = plusieurs lecteurs simultanés sans bloquer l'écrivain
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))
            await conn.execute(text("PRAGMA cache_size=-64000"))  # 64MB cache
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
        await conn.run_sync(Base.metadata.create_all)