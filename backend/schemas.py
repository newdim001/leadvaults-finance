from __future__ import annotations

import datetime
from pydantic import BaseModel
from typing import Optional, List


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    username: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


# ─── Categories ───

class CategoryCreate(BaseModel):
    name: str
    type: str


class CategoryOut(BaseModel):
    id: int
    name: str
    type: str
    model_config = {"from_attributes": True}


# ─── Family Members ───

class MemberCreate(BaseModel):
    name: str


class MemberOut(BaseModel):
    id: int
    name: str
    model_config = {"from_attributes": True}


# ─── Transactions ───

class TransactionCreate(BaseModel):
    date: str
    amount: float
    type: str
    description: Optional[str] = None
    tags: Optional[str] = None
    category_id: int
    member_id: int
    account_id: Optional[int] = None


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
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    model_config = {"from_attributes": True}


# ─── Recurring Templates ───

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


# ─── Accounts ───

class AccountCreate(BaseModel):
    name: str
    type: str
    icon: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    icon: Optional[str] = None


class AccountOut(BaseModel):
    id: int
    name: str
    type: str
    currency: str = "USD"
    balance: float = 0.0
    icon: Optional[str] = None
    model_config = {"from_attributes": True}


# ─── Budgets ───

class BudgetCreate(BaseModel):
    category_id: int
    amount: float
    month: int
    year: int


class BudgetOut(BaseModel):
    id: int
    category_id: int
    category_name: str = ""
    month: int
    year: int
    amount: float
    spent: float = 0.0
    remaining: float = 0.0
    percentage: float = 0.0
    model_config = {"from_attributes": True}


class BudgetSummaryCategory(BaseModel):
    name: str
    budgeted: float
    spent: float
    percentage: float


class BudgetSummary(BaseModel):
    total_budget: float = 0.0
    total_spent: float = 0.0
    remaining: float = 0.0
    categories: List[BudgetSummaryCategory] = []


# ─── Attachments ───

class AttachmentOut(BaseModel):
    id: int
    transaction_id: int
    filename: str
    mime_type: Optional[str] = None
    model_config = {"from_attributes": True}


# ─── Metal Inventory ───

class MetalCreate(BaseModel):
    metal_type: str
    form: str
    weight_grams: float
    purity: float
    cost_basis: float
    purchase_date: Optional[str] = None
    storage_location: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "owned"


class MetalUpdate(BaseModel):
    metal_type: Optional[str] = None
    form: Optional[str] = None
    weight_grams: Optional[float] = None
    purity: Optional[float] = None
    cost_basis: Optional[float] = None
    current_value: Optional[float] = None
    purchase_date: Optional[str] = None
    storage_location: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class MetalOut(BaseModel):
    id: int
    metal_type: str
    form: str
    weight_grams: float
    purity: float
    cost_basis: float
    current_value: float
    purchase_date: Optional[str] = None
    storage_location: Optional[str] = None
    notes: Optional[str] = None
    status: str = "owned"
    model_config = {"from_attributes": True}


class MetalSummaryItem(BaseModel):
    metal_type: str
    total_weight: float
    total_value: float
    total_cost: float
    gain_loss: float
    item_count: int


class MetalSummary(BaseModel):
    items: List[MetalSummaryItem] = []
    grand_total_weight: float = 0.0
    grand_total_value: float = 0.0
    grand_total_cost: float = 0.0
    grand_gain_loss: float = 0.0


# ─── Reports ───

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
