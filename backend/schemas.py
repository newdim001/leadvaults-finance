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
    category_id: int
    member_id: int


class TransactionOut(BaseModel):
    id: int
    date: str
    amount: float
    type: str
    description: Optional[str] = None
    category_id: int
    category_name: str = ""
    member_id: int
    member_name: str = ""
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
