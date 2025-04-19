import datetime
import os

from sqlalchemy import (JSON, Column, DateTime, Float, Integer, String,
                        create_engine)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./paystubs.db")
engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    ),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Paystub(Base):
    __tablename__ = "paystubs"
    id = Column(Integer, primary_key=True, index=True)
    period_start = Column(String, index=True)
    period_end = Column(String, index=True)
    gross_pay = Column(Float)
    net_pay = Column(Float)
    taxes = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
