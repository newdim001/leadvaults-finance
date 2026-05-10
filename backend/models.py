from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    member_id = Column(Integer, ForeignKey("family_members.id"), nullable=True)
    role = Column(String, nullable=False, default="member")  # admin, member
    created_at = Column(DateTime, server_default=func.now())

    member = relationship("FamilyMember", foreign_keys=[member_id])


class FamilyMember(Base):
    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    transactions = relationship("Transaction", back_populates="member")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # income, expense, investment
    created_at = Column(DateTime, server_default=func.now())

    transactions = relationship("Transaction", back_populates="category")


class RecurringTemplate(Base):
    __tablename__ = "recurring_templates"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="AED")
    type = Column(String, nullable=False)  # income, expense, investment
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("family_members.id"), nullable=False)
    description = Column(String, nullable=True)
    tags = Column(String, nullable=True)
    day_of_month = Column(Integer, nullable=False, default=1)
    active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now())

    category = relationship("Category")
    member = relationship("FamilyMember")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # bank, credit_card, cash, metal_vault, investment
    currency = Column(String, default="USD")
    balance = Column(Float, default=0.0)
    icon = Column(String, nullable=True)  # emoji
    created_at = Column(DateTime, server_default=func.now())


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id = Column(Integer, primary_key=True, index=True)
    from_currency = Column(String, nullable=False)
    to_currency = Column(String, nullable=False)
    rate = Column(Float, nullable=False)
    updated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("from_currency", "to_currency"),)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="AED")
    amount_aed = Column(Float, nullable=True)  # converted to base currency AED
    type = Column(String, nullable=False)  # income, expense, investment
    description = Column(String, nullable=True)
    tags = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("family_members.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, default=None)
    created_at = Column(DateTime, server_default=func.now())

    category = relationship("Category", back_populates="transactions")
    member = relationship("FamilyMember", back_populates="transactions")
    account = relationship("Account")
    attachments = relationship("TransactionAttachment", back_populates="transaction", cascade="all, delete-orphan")


class TransactionAttachment(Base):
    __tablename__ = "transaction_attachments"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    mime_type = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    transaction = relationship("Transaction", back_populates="attachments")


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    month = Column(Integer, nullable=False)  # 1-12
    year = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    category = relationship("Category")

    __table_args__ = (UniqueConstraint("category_id", "month", "year"),)


class MetalInventory(Base):
    __tablename__ = "metal_inventory"

    id = Column(Integer, primary_key=True, index=True)
    metal_type = Column(String, nullable=False)  # gold, silver, platinum, palladium, copper
    form = Column(String, nullable=False)  # bar, coin, jewelry, scrap
    weight_grams = Column(Float, nullable=False)
    purity = Column(Float, nullable=False)  # 0.0-1.0 (24K = 1.0)
    cost_basis = Column(Float, nullable=False)
    current_value = Column(Float, default=0.0)
    purchase_date = Column(Date, nullable=True)
    storage_location = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    status = Column(String, default="owned")  # owned, sold
    created_at = Column(DateTime, server_default=func.now())
