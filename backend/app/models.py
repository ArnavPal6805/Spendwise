from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, Numeric, Boolean, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_transaction_fingerprint"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(500), index=True)
    merchant: Mapped[str] = mapped_column(String(200), default="Unknown", index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2)) # positive=expense, negative=income/refund
    category: Mapped[str] = mapped_column(String(80), default="Uncategorized", index=True)
    account: Mapped[str] = mapped_column(String(120), default="Imported statement")
    source_file: Mapped[str] = mapped_column(String(255), default="upload")
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_duplicate_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[str] = mapped_column(String(7), index=True) # YYYY-MM
    category: Mapped[str] = mapped_column(String(80), index=True)
    limit_amount: Mapped[float] = mapped_column(Numeric(12, 2))

class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant: Mapped[str] = mapped_column(String(200), index=True)
    typical_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    cadence: Mapped[str] = mapped_column(String(30), default="monthly")
    last_charge: Mapped[date] = mapped_column(Date)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=2)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
