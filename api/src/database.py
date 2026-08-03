from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config import settings

# pool_pre_ping matters more than it looks, and it became necessary the day Aurora was
# allowed to scale to zero. A warm Lambda keeps its pooled connections between
# invocations; the cluster pauses after ten idle minutes and every one of those
# connections dies silently. Without a ping, the next request hands out a corpse and the
# caller gets a 500 — exactly the error seen when a host tried to sign in during a
# pause-and-restart. Pre-ping costs one trivial round trip and replaces dead connections
# transparently.
#
# pool_recycle keeps a connection from lingering across a pause in the first place, and
# connect_timeout leaves room for a resume — which takes around fifteen seconds — inside
# the Lambda's 29 s ceiling.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"connect_timeout": 20},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
