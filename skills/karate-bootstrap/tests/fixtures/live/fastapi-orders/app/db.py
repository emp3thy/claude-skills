"""Engine and session factory, built once from the settings.

``create_engine`` does not open a connection; SQLAlchemy connects lazily on first use, so this
module is safe to import before Postgres is reachable.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
