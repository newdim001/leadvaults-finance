from __future__ import annotations

import datetime
from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    username: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CategoryCreate(BaseModel):
    name: str
    type: str


class CategoryOut(BaseModel):
    id: int
    name: str
    type: str
    model_config = {"from_attributes": True}


class MemberCreate(BaseModel):
    name: str


class MemberOut(BaseModel):
    id: int
    name: str
    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    date: str
    amount: float
    type: str
    description: Optional[str] = None
    tags: Optional[str] = None
    category_id: int
    member_id: int


class TransactionOut(BaseModel):
    id: int
    date: str
    amount: float
    type: str
    description: Optional[str] = None
    tags: Optional[str] = None
    category_id: int
    category_name: str = ""
    member_id: int
    member_name: str = ""
    model_config = {"from_attributes": True}


class RecurringTemplateCreate(BaseModel):
    label: str
    amount: float
    type: str
    category_id: int
    member_id: int
    description: Optional[str] = None
    tags: Optional[str] = None
    day_of_month: int = 1


class RecurringTemplateOut(BaseModel):
    id: int
    label: str
    amount: float
    type: str
    category_id: int
    category_name: str = ""
    member_id: int
    member_name: str = ""
    description: Optional[str] = None
    tags: Optional[str] = None
    day_of_month: int
    active: int
    model_config = {"from_attributes": True}


class MonthlySummary(BaseModel):
    month: str
    income: float = 0
    expense: float = 0
    investment: float = 0
    net: float = 0


class CategoryBreakdown(BaseModel):
    category: str
    amount: float
    percentage: float


class MemberBreakdown(BaseModel):
    member: str
    income: float = 0
    expense: float = 0
    investment: float = 0


class NetWorthPoint(BaseModel):
    month: str
    net_worth: float
    total_income: float = 0
    total_expense: float = 0
    total_investment: float = 0


class PortfolioHolding(BaseModel):
    category: str
    cost_basis: float
    current_value: float = 0
    gain_loss: float = 0
    gain_loss_pct: float = 0
    allocation_pct: float = 0
