from __future__ import annotations
import os
import datetime
import csv
import io
import math
import uuid
import json
import urllib.request
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import func, extract, and_
from sqlalchemy.orm import Session
from jose import jwt, JWTError

import bcrypt as _bcrypt
class _PwdCtx:
    def hash(self, secret): return _bcrypt.hashpw(secret.encode(), _bcrypt.gensalt()).decode()
    def verify(self, secret, hash): return _bcrypt.checkpw(secret.encode(), hash.encode())
pwd_ctx = _PwdCtx()

from database import engine, Base, get_db, SessionLocal
from models import (
    User, FamilyMember, Category, Transaction, RecurringTemplate,
    Account, Budget, TransactionAttachment, MetalInventory,
    ExchangeRate,
)
from schemas import (
    LoginRequest, TokenResponse, ChangePasswordRequest, RegisterRequest,
    UserOut, CreateUserRequest,
    CategoryCreate, CategoryOut,
    MemberCreate, MemberOut,
    TransactionCreate, TransactionOut,
    RecurringTemplateCreate, RecurringTemplateOut,
    AccountCreate, AccountUpdate, AccountOut,
    BudgetCreate, BudgetOut, BudgetSummary, BudgetSummaryCategory,
    AttachmentOut,
    MetalCreate, MetalUpdate, MetalOut, MetalSummary, MetalSummaryItem,
    MonthlySummary, CategoryBreakdown, MemberBreakdown,
    NetWorthPoint, PortfolioHolding,
    ExchangeRateOut,
)

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-v3")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 90
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

Base.metadata.create_all(bind=engine)
security = HTTPBearer(auto_error=False)

app = FastAPI(title="Lead Vaults Finance")

METAL_PRICES = {
    "gold": 85.0,
    "silver": 1.0,
    "platinum": 30.0,
    "palladium": 35.0,
    "copper": 0.009,
}

BASE_CURRENCY = "AED"
CURRENCIES = ["AED", "USD", "EUR"]
CURRENCY_SYMBOLS = {"AED": "د.إ", "USD": "$", "EUR": "€"}

DEFAULT_RATES = {
    ("AED", "USD"): 0.2723,
    ("AED", "EUR"): 0.2518,
    ("USD", "AED"): 3.6725,
    ("USD", "EUR"): 0.9247,
    ("EUR", "AED"): 3.9714,
    ("EUR", "USD"): 1.0814,
}


def get_exchange_rate(from_curr: str, to_curr: str, db: Session) -> float:
    if from_curr == to_curr:
        return 1.0
    rate_obj = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == from_curr,
        ExchangeRate.to_currency == to_curr
    ).first()
    if rate_obj:
        return rate_obj.rate
    # Fallback to default
    return DEFAULT_RATES.get((from_curr, to_curr), 1.0)


def convert_to_base(amount: float, currency: str, db: Session) -> float:
    """Convert amount from given currency to BASE_CURRENCY (AED)."""
    if currency == BASE_CURRENCY:
        return amount
    rate = get_exchange_rate(currency, BASE_CURRENCY, db)
    return amount * rate


def fmt_currency(amount: float, currency: str) -> str:
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    return f"{symbol}{amount:,.2f}"


def create_token(username: str) -> str:
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(401, "Not authenticated")
    username = verify_token(credentials.credentials)
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(401, "User not found")
    return user


def seed_data():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(username="admin", password_hash=pwd_ctx.hash("admin123"), role="admin"))
        if db.query(FamilyMember).count() == 0:
            db.add_all([FamilyMember(name="Suren"), FamilyMember(name="Partner")])
        if db.query(Category).count() == 0:
            cats = [
                Category(name="Salary", type="income"),
                Category(name="Freelance", type="income"),
                Category(name="Passive Income", type="income"),
                Category(name="Other Income", type="income"),
                Category(name="Groceries", type="expense"),
                Category(name="Rent", type="expense"),
                Category(name="Utilities", type="expense"),
                Category(name="Transport", type="expense"),
                Category(name="Dining Out", type="expense"),
                Category(name="Shopping", type="expense"),
                Category(name="Healthcare", type="expense"),
                Category(name="Entertainment", type="expense"),
                Category(name="Education", type="expense"),
                Category(name="Other Expense", type="expense"),
                Category(name="Stocks", type="investment"),
                Category(name="Mutual Funds", type="investment"),
                Category(name="Crypto", type="investment"),
                Category(name="Gold", type="investment"),
                Category(name="Other Investment", type="investment"),
            ]
            db.add_all(cats)
        if db.query(Account).count() == 0:
            db.add_all([
                Account(name="Main Bank Account", type="bank", icon="\U0001f3e6"),
                Account(name="Cash", type="cash", icon="\U0001f4b5"),
                Account(name="Gold Vault", type="metal_vault", icon="\U0001f947"),
                Account(name="Credit Card", type="credit_card", icon="\U0001f4b3"),
                Account(name="Investment Account", type="investment", icon="\U0001f4c8"),
            ])
        if db.query(ExchangeRate).count() == 0:
            db.add_all([
                ExchangeRate(from_currency=f, to_currency=t, rate=r)
                for (f, t), r in DEFAULT_RATES.items()
            ])
        db.commit()
    finally:
        db.close()

seed_data()


def _tx_out(t: Transaction) -> TransactionOut:
    return TransactionOut(
        id=t.id, date=t.date.isoformat(), amount=t.amount,
        currency=t.currency or "AED", amount_aed=t.amount_aed,
        type=t.type,
        description=t.description, tags=t.tags,
        category_id=t.category_id, category_name=t.category.name,
        member_id=t.member_id, member_name=t.member.name,
        account_id=t.account_id,
        account_name=t.account.name if t.account else None,
    )


# ─── Auth ───
@app.post("/api/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not pwd_ctx.verify(req.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    member_name = user.member.name if user.member else None
    return TokenResponse(
        token=create_token(user.username),
        username=user.username,
        role=user.role,
        member_id=user.member_id,
        member_name=member_name,
    )


@app.post("/api/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(400, "Username already taken")
    if len(req.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    # Create a family member named after the user
    member = FamilyMember(name=req.username.capitalize())
    db.add(member); db.flush()
    user = User(username=req.username, password_hash=pwd_ctx.hash(req.password),
        role="member", member_id=member.id)
    db.add(user); db.commit(); db.refresh(user)
    return TokenResponse(
        token=create_token(user.username),
        username=user.username,
        role="member",
        member_id=user.member_id,
        member_name=member.name,
    )


@app.post("/api/auth/change-password")
def change_password(req: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not pwd_ctx.verify(req.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if len(req.new_password) < 4:
        raise HTTPException(400, "New password must be at least 4 characters")
    user.password_hash = pwd_ctx.hash(req.new_password)
    db.commit()
    return {"ok": True, "message": "Password changed successfully"}


@app.get("/api/auth/check")
def check_auth(user: User = Depends(get_current_user)):
    member_name = user.member.name if user.member else None
    return {"ok": True, "username": user.username, "role": user.role,
        "member_id": user.member_id, "member_name": member_name}


# ─── User Management (Admin only) ───
@app.get("/api/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(get_current_user)):
    if admin.role != "admin":
        raise HTTPException(403, "Admin access required")
    users = db.query(User).all()
    result = []
    for u in users:
        result.append(UserOut(id=u.id, username=u.username, role=u.role,
            member_id=u.member_id, member_name=u.member.name if u.member else None))
    return result


@app.post("/api/users", response_model=UserOut)
def create_user(req: CreateUserRequest, db: Session = Depends(get_db), admin: User = Depends(get_current_user)):
    if admin.role != "admin":
        raise HTTPException(403, "Admin access required")
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(400, "Username already taken")
    member = db.query(FamilyMember).get(req.member_id)
    if not member:
        raise HTTPException(400, "Family member not found")
    user_exists = db.query(User).filter(User.member_id == req.member_id).first()
    if user_exists:
        raise HTTPException(400, f"'{member.name}' already has a user account")
    if len(req.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    db_user = User(username=req.username, password_hash=pwd_ctx.hash(req.password),
        member_id=req.member_id, role="member")
    db.add(db_user); db.commit(); db.refresh(db_user)
    return UserOut(id=db_user.id, username=db_user.username, role=db_user.role,
        member_id=db_user.member_id, member_name=member.name)


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_user)):
    if admin.role != "admin":
        raise HTTPException(403, "Admin access required")
    if user_id == admin.id:
        raise HTTPException(400, "Cannot delete yourself")
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(404)
    db.delete(user); db.commit()
    return {"ok": True}


# ─── Categories ───
@app.get("/api/categories", response_model=List[CategoryOut])
def list_categories(type: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Category)
    if type: q = q.filter(Category.type == type)
    return q.order_by(Category.name).all()


@app.post("/api/categories", response_model=CategoryOut)
def create_category(cat: CategoryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = db.query(Category).filter(Category.name == cat.name, Category.type == cat.type).first()
    if existing: raise HTTPException(400, "Category already exists")
    db_cat = Category(name=cat.name, type=cat.type)
    db.add(db_cat); db.commit(); db.refresh(db_cat)
    return db_cat


@app.delete("/api/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cat = db.query(Category).get(cat_id)
    if not cat: raise HTTPException(404)
    if db.query(Transaction).filter(Transaction.category_id == cat_id).count():
        raise HTTPException(400, "Category has transactions")
    db.delete(cat); db.commit()
    return {"ok": True}


# ─── Members ───
@app.get("/api/members", response_model=List[MemberOut])
def list_members(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(FamilyMember).order_by(FamilyMember.name).all()


@app.post("/api/members", response_model=MemberOut)
def create_member(m: MemberCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = db.query(FamilyMember).filter(FamilyMember.name == m.name).first()
    if existing: raise HTTPException(400, "Member already exists")
    db_m = FamilyMember(name=m.name)
    db.add(db_m); db.commit(); db.refresh(db_m)
    return db_m


@app.delete("/api/members/{member_id}")
def delete_member(member_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    m = db.query(FamilyMember).get(member_id)
    if not m: raise HTTPException(404)
    if db.query(Transaction).filter(Transaction.member_id == member_id).count():
        raise HTTPException(400, "Member has transactions")
    db.delete(m); db.commit()
    return {"ok": True}


# ─── Accounts ───
@app.get("/api/accounts", response_model=List[AccountOut])
def list_accounts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    accounts = db.query(Account).order_by(Account.name).all()
    result = []
    for a in accounts:
        inc = float(db.query(func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).filter(
            Transaction.account_id == a.id, Transaction.type == "income").scalar() or 0)
        exp = float(db.query(func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).filter(
            Transaction.account_id == a.id, Transaction.type == "expense").scalar() or 0)
        inv = float(db.query(func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).filter(
            Transaction.account_id == a.id, Transaction.type == "investment").scalar() or 0)
        result.append(AccountOut(id=a.id, name=a.name, type=a.type,
            currency=a.currency, balance=round(inc - exp - inv, 2), icon=a.icon))
    return result


@app.post("/api/accounts", response_model=AccountOut)
def create_account(a: AccountCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db_a = Account(name=a.name, type=a.type, icon=a.icon)
    db.add(db_a); db.commit(); db.refresh(db_a)
    return AccountOut(id=db_a.id, name=db_a.name, type=db_a.type, currency=db_a.currency, balance=0, icon=db_a.icon)


@app.put("/api/accounts/{acc_id}", response_model=AccountOut)
def update_account(acc_id: int, a: AccountUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db_a = db.query(Account).get(acc_id)
    if not db_a: raise HTTPException(404)
    if a.name is not None: db_a.name = a.name
    if a.type is not None: db_a.type = a.type
    if a.icon is not None: db_a.icon = a.icon
    db.commit(); db.refresh(db_a)
    return AccountOut(id=db_a.id, name=db_a.name, type=db_a.type, currency=db_a.currency, balance=db_a.balance, icon=db_a.icon)


@app.delete("/api/accounts/{acc_id}")
def delete_account(acc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.query(Account).get(acc_id)
    if not a: raise HTTPException(404)
    if db.query(Transaction).filter(Transaction.account_id == acc_id).count():
        raise HTTPException(400, "Account has transactions")
    db.delete(a); db.commit()
    return {"ok": True}


# ─── Transactions ───
@app.get("/api/transactions", response_model=List[TransactionOut])
def list_transactions(year: Optional[int] = None, month: Optional[int] = None,
    type: Optional[str] = None, member_id: Optional[int] = None,
    tag: Optional[str] = None, limit: int = 200, offset: int = 0,
    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Transaction)
    if year: q = q.filter(extract("year", Transaction.date) == year)
    if month: q = q.filter(extract("month", Transaction.date) == month)
    if type: q = q.filter(Transaction.type == type)
    if member_id: q = q.filter(Transaction.member_id == member_id)
    if tag: q = q.filter(Transaction.tags.contains(tag))
    q = q.order_by(Transaction.date.desc(), Transaction.id.desc())
    return [_tx_out(t) for t in q.offset(offset).limit(limit).all()]


@app.post("/api/transactions", response_model=TransactionOut)
def create_transaction(t: TransactionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cat = db.query(Category).get(t.category_id)
    if not cat: raise HTTPException(400, "Category not found")
    mem = db.query(FamilyMember).get(t.member_id)
    if not mem: raise HTTPException(400, "Member not found")
    if t.account_id:
        if not db.query(Account).get(t.account_id): raise HTTPException(400, "Account not found")
    try: dt = datetime.date.fromisoformat(t.date)
    except: raise HTTPException(400, "Invalid date")
    currency = t.currency or "AED"
    amount_aed = convert_to_base(t.amount, currency, db)
    db_t = Transaction(date=dt, amount=t.amount, currency=currency, amount_aed=amount_aed, type=t.type,
        description=t.description, tags=t.tags,
        category_id=t.category_id, member_id=t.member_id, account_id=t.account_id)
    db.add(db_t); db.commit(); db.refresh(db_t)
    return _tx_out(db_t)


@app.put("/api/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(tx_id: int, t: TransactionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db_t = db.query(Transaction).get(tx_id)
    if not db_t: raise HTTPException(404)
    if not db.query(Category).get(t.category_id): raise HTTPException(400, "Category not found")
    if not db.query(FamilyMember).get(t.member_id): raise HTTPException(400, "Member not found")
    if t.account_id and not db.query(Account).get(t.account_id): raise HTTPException(400, "Account not found")
    try: dt = datetime.date.fromisoformat(t.date)
    except: raise HTTPException(400, "Invalid date")
    db_t.date = dt; db_t.amount = t.amount; db_t.type = t.type
    db_t.currency = t.currency or "AED"
    db_t.amount_aed = convert_to_base(t.amount, db_t.currency, db)
    db_t.description = t.description; db_t.tags = t.tags
    db_t.category_id = t.category_id; db_t.member_id = t.member_id
    db_t.account_id = t.account_id
    db.commit(); db.refresh(db_t)
    return _tx_out(db_t)


@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.query(Transaction).get(tx_id)
    if not t: raise HTTPException(404)
    for att in t.attachments:
        if os.path.exists(att.filepath):
            try: os.remove(att.filepath)
            except: pass
        db.delete(att)
    db.delete(t); db.commit()
    return {"ok": True}


@app.get("/api/transactions/export/csv")
def export_csv(year: Optional[int] = None, month: Optional[int] = None,
    type: Optional[str] = None, tag: Optional[str] = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Transaction)
    if year: q = q.filter(extract("year", Transaction.date) == year)
    if month: q = q.filter(extract("month", Transaction.date) == month)
    if type: q = q.filter(Transaction.type == type)
    if tag: q = q.filter(Transaction.tags.contains(tag))
    q = q.order_by(Transaction.date.desc()).all()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Date","Type","Category","Member","Amount","Currency","AED Amount","Description","Tags","Account"])
    for t in q:
        w.writerow([t.date.isoformat(), t.type, t.category.name, t.member.name,
            t.amount, t.currency or "AED", t.amount_aed or t.amount,
            t.description or "", t.tags or "", t.account.name if t.account else ""])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"})


# ─── Exchange Rates ───
@app.get("/api/exchange-rates", response_model=List[ExchangeRateOut])
def list_exchange_rates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(ExchangeRate).order_by(ExchangeRate.from_currency, ExchangeRate.to_currency).all()


@app.put("/api/exchange-rates/{from_curr}/{to_curr}")
def update_exchange_rate(from_curr: str, to_curr: str, rate: float = Query(...),
    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if from_curr not in CURRENCIES or to_curr not in CURRENCIES:
        raise HTTPException(400, "Invalid currency")
    if rate <= 0:
        raise HTTPException(400, "Rate must be positive")
    er = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == from_curr,
        ExchangeRate.to_currency == to_curr
    ).first()
    if er:
        er.rate = rate
    else:
        er = ExchangeRate(from_currency=from_curr, to_currency=to_curr, rate=rate)
        db.add(er)
    db.commit(); db.refresh(er)
    # Update all existing transactions with new conversion
    txs = db.query(Transaction).filter(
        Transaction.currency == from_curr
    ).all()
    for tx in txs:
        tx.amount_aed = convert_to_base(tx.amount, tx.currency, db)
    db.commit()
    return {"ok": True, "from_currency": from_curr, "to_currency": to_curr, "rate": er.rate}


@app.get("/api/currencies")
def list_currencies():
    return {
        "base": BASE_CURRENCY,
        "currencies": CURRENCIES,
        "symbols": CURRENCY_SYMBOLS,
    }


FX_API_URL = "https://api.frankfurter.app/latest?from=AED&to=USD,EUR"
FX_API_FALLBACK = "https://open.er-api.com/v6/latest/AED"


def _save_rate(from_curr: str, to_curr: str, rate: float, db: Session):
    er = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == from_curr,
        ExchangeRate.to_currency == to_curr
    ).first()
    if er:
        er.rate = rate
    else:
        er = ExchangeRate(from_currency=from_curr, to_currency=to_curr, rate=rate)
        db.add(er)


def _recalc_all_tx(db: Session):
    txs = db.query(Transaction).filter(Transaction.currency != BASE_CURRENCY).all()
    for tx in txs:
        tx.amount_aed = convert_to_base(tx.amount, tx.currency or "AED", db)
    db.commit()


@app.post("/api/exchange-rates/refresh")
async def refresh_exchange_rates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    errors = []
    data = None
    # Try Frankfurter API first
    for url in [FX_API_URL, FX_API_FALLBACK]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LeadVaultsFinance/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            if "rates" in data:
                break
        except Exception as e:
            errors.append(f"{url}: {str(e)}")
            continue

    if not data or "rates" not in data:
        raise HTTPException(502, f"Failed to fetch live rates. Errors: {'; '.join(errors)}")

    rates = data["rates"]
    base = data.get("base", "AED")
    base_to_currencies = {}

    if base == "AED":
        for curr in CURRENCIES:
            if curr == "AED":
                continue
            rate_to = rates.get(curr)
            if rate_to:
                base_to_currencies[curr] = rate_to
    else:
        # Fallback: Frankfurter base might be EUR; open.er-api returns base=AED
        eur_rate = rates.get("EUR")
        usd_rate = rates.get("USD")
        aed_rate = rates.get("AED")
        if eur_rate:
            base_to_currencies["EUR"] = eur_rate
        if usd_rate:
            base_to_currencies["USD"] = usd_rate

    if not base_to_currencies:
        raise HTTPException(502, "Could not parse exchange rates from API response")

    # Update all 6 rate pairs
    for target, rate_to in base_to_currencies.items():
        rate_from = round(1.0 / rate_to, 6) if rate_to > 0 else 1.0
        _save_rate("AED", target, round(rate_to, 6), db)
        _save_rate(target, "AED", rate_from, db)

    # Derive cross rates (USD ↔ EUR)
    aed_to_usd = base_to_currencies.get("USD", 1.0)
    aed_to_eur = base_to_currencies.get("EUR", 1.0)
    if aed_to_usd > 0:
        usd_to_eur = round(aed_to_eur / aed_to_usd, 6)
        eur_to_usd = round(1.0 / usd_to_eur, 6) if usd_to_eur > 0 else 1.0
        _save_rate("USD", "EUR", usd_to_eur, db)
        _save_rate("EUR", "USD", eur_to_usd, db)

    db.commit()

    # Recalculate all existing transactions
    _recalc_all_tx(db)

    # Return updated rates
    updated = db.query(ExchangeRate).order_by(ExchangeRate.from_currency, ExchangeRate.to_currency).all()
    return {
        "ok": True,
        "source": "live",
        "rates": [{"from_currency": r.from_currency, "to_currency": r.to_currency, "rate": r.rate} for r in updated]
    }


# ─── Attachments ───
@app.get("/api/transactions/{tx_id}/attachments", response_model=List[AttachmentOut])
def list_attachments(tx_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tx = db.query(Transaction).get(tx_id)
    if not tx: raise HTTPException(404)
    return [AttachmentOut(id=a.id, transaction_id=a.transaction_id, filename=a.filename, mime_type=a.mime_type) for a in tx.attachments]


@app.post("/api/transactions/{tx_id}/attachments")
async def upload_attachments(tx_id: int, files: List[UploadFile] = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tx = db.query(Transaction).get(tx_id)
    if not tx: raise HTTPException(404)
    tx_dir = os.path.join(UPLOAD_DIR, str(tx_id))
    os.makedirs(tx_dir, exist_ok=True)
    uploaded = []
    for f in files:
        ext = os.path.splitext(f.filename or "file")[1]
        safe_name = str(uuid.uuid4()) + ext
        filepath = os.path.join(tx_dir, safe_name)
        content = await f.read()
        with open(filepath, "wb") as out:
            out.write(content)
        att = TransactionAttachment(transaction_id=tx_id, filename=f.filename or "file",
            filepath=filepath, mime_type=f.content_type)
        db.add(att); db.commit(); db.refresh(att)
        uploaded.append(AttachmentOut(id=att.id, transaction_id=att.transaction_id, filename=att.filename, mime_type=att.mime_type))
    return uploaded


@app.get("/api/attachments/{att_id}/download")
def download_attachment(att_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    att = db.query(TransactionAttachment).get(att_id)
    if not att: raise HTTPException(404)
    if not os.path.exists(att.filepath): raise HTTPException(404, "File not found")
    return FileResponse(att.filepath, filename=att.filename, media_type=att.mime_type or "application/octet-stream")


@app.delete("/api/attachments/{att_id}")
def delete_attachment(att_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    att = db.query(TransactionAttachment).get(att_id)
    if not att: raise HTTPException(404)
    if os.path.exists(att.filepath):
        try: os.remove(att.filepath)
        except: pass
    db.delete(att); db.commit()
    return {"ok": True}


# ─── Recurring ───
@app.get("/api/recurring", response_model=List[RecurringTemplateOut])
def list_recurring(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    templates = db.query(RecurringTemplate).order_by(RecurringTemplate.day_of_month).all()
    result = []
    for r in templates:
        cat = db.query(Category).get(r.category_id)
        mem = db.query(FamilyMember).get(r.member_id)
        result.append(RecurringTemplateOut(id=r.id, label=r.label, amount=r.amount,
            currency=r.currency or "AED", type=r.type,
            category_id=r.category_id, category_name=cat.name if cat else "",
            member_id=r.member_id, member_name=mem.name if mem else "",
            description=r.description, tags=r.tags, day_of_month=r.day_of_month, active=r.active))
    return result


@app.post("/api/recurring", response_model=RecurringTemplateOut)
def create_recurring(r: RecurringTemplateCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cat = db.query(Category).get(r.category_id)
    if not cat: raise HTTPException(400, "Category not found")
    mem = db.query(FamilyMember).get(r.member_id)
    if not mem: raise HTTPException(400, "Member not found")
    if r.day_of_month < 1 or r.day_of_month > 28: raise HTTPException(400, "Day must be 1-28")
    db_r = RecurringTemplate(label=r.label, amount=r.amount, currency=r.currency or "AED", type=r.type,
        category_id=r.category_id, member_id=r.member_id,
        description=r.description, tags=r.tags, day_of_month=r.day_of_month)
    db.add(db_r); db.commit(); db.refresh(db_r)
    return RecurringTemplateOut(id=db_r.id, label=db_r.label, amount=db_r.amount,
        currency=db_r.currency or "AED",
        type=db_r.type, category_id=db_r.category_id, category_name=cat.name,
        member_id=db_r.member_id, member_name=mem.name,
        description=db_r.description, tags=db_r.tags, day_of_month=db_r.day_of_month, active=db_r.active)


@app.delete("/api/recurring/{r_id}")
def delete_recurring(r_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(RecurringTemplate).get(r_id)
    if not r: raise HTTPException(404)
    db.delete(r); db.commit()
    return {"ok": True}


@app.post("/api/recurring/process")
def process_recurring(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today = datetime.date.today()
    templates = db.query(RecurringTemplate).filter(RecurringTemplate.active == 1).all()
    created = 0
    for r in templates:
        target_day = min(r.day_of_month, 28)
        try: scheduled = today.replace(day=target_day)
        except: continue
        if scheduled > today: continue
        existing = db.query(Transaction).filter(Transaction.description == r.description,
            Transaction.type == r.type, Transaction.amount == r.amount,
            Transaction.category_id == r.category_id, Transaction.member_id == r.member_id,
            extract("year", Transaction.date) == today.year,
            extract("month", Transaction.date) == today.month).first()
        if existing: continue
        currency = r.currency or "AED"
        amount_aed = convert_to_base(r.amount, currency, db)
        db_t = Transaction(date=scheduled, amount=r.amount, currency=currency, amount_aed=amount_aed,
            type=r.type, description=r.description or r.label, tags=r.tags,
            category_id=r.category_id, member_id=r.member_id)
        db.add(db_t); created += 1
    if created: db.commit()
    return {"ok": True, "created": created}


# ─── Budgets ───
@app.get("/api/budgets", response_model=List[BudgetOut])
def list_budgets(year: int, month: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    budgets = db.query(Budget).filter(Budget.year == year, Budget.month == month).all()
    result = []
    for b in budgets:
        cat = db.query(Category).get(b.category_id)
        spent = float(db.query(func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).filter(
            Transaction.category_id == b.category_id, Transaction.type == "expense",
            extract("year", Transaction.date) == year,
            extract("month", Transaction.date) == month).scalar() or 0)
        result.append(BudgetOut(id=b.id, category_id=b.category_id,
            category_name=cat.name if cat else "", month=b.month, year=b.year, amount=b.amount,
            spent=round(spent, 2), remaining=round(b.amount - spent, 2),
            percentage=round(min(spent / b.amount * 100, 100), 1) if b.amount > 0 else 0))
    return result


@app.post("/api/budgets", response_model=BudgetOut)
def create_budget(b: BudgetCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cat = db.query(Category).get(b.category_id)
    if not cat: raise HTTPException(400, "Category not found")
    if b.month < 1 or b.month > 12: raise HTTPException(400, "Invalid month")
    existing = db.query(Budget).filter(Budget.category_id == b.category_id,
        Budget.month == b.month, Budget.year == b.year).first()
    if existing:
        existing.amount = b.amount; db.commit(); db.refresh(existing)
        budget = existing
    else:
        budget = Budget(category_id=b.category_id, amount=b.amount, month=b.month, year=b.year)
        db.add(budget); db.commit(); db.refresh(budget)
    spent = float(db.query(func.sum(Transaction.amount)).filter(
        Transaction.category_id == b.category_id, Transaction.type == "expense",
        extract("year", Transaction.date) == b.year,
        extract("month", Transaction.date) == b.month).scalar() or 0)
    return BudgetOut(id=budget.id, category_id=budget.category_id, category_name=cat.name,
        month=budget.month, year=budget.year, amount=budget.amount,
        spent=round(spent, 2), remaining=round(budget.amount - spent, 2),
        percentage=round(min(spent / budget.amount * 100, 100), 1) if budget.amount > 0 else 0)


@app.delete("/api/budgets/{b_id}")
def delete_budget(b_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = db.query(Budget).get(b_id)
    if not b: raise HTTPException(404)
    db.delete(b); db.commit()
    return {"ok": True}


@app.get("/api/budgets/summary", response_model=BudgetSummary)
def budget_summary(year: int, month: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    budgets = db.query(Budget).filter(Budget.year == year, Budget.month == month).all()
    total_budget = 0.0; total_spent = 0.0; categories = []
    for b in budgets:
        cat = db.query(Category).get(b.category_id)
        spent = float(db.query(func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).filter(
            Transaction.category_id == b.category_id, Transaction.type == "expense",
            extract("year", Transaction.date) == year,
            extract("month", Transaction.date) == month).scalar() or 0)
        total_budget += b.amount; total_spent += spent
        categories.append(BudgetSummaryCategory(name=cat.name if cat else "Unknown",
            budgeted=b.amount, spent=round(spent, 2),
            percentage=round(min(spent / b.amount * 100, 100), 1) if b.amount > 0 else 0))
    return BudgetSummary(total_budget=round(total_budget, 2), total_spent=round(total_spent, 2),
        remaining=round(total_budget - total_spent, 2), categories=categories)


# ─── Metals ───
@app.get("/api/metals", response_model=List[MetalOut])
def list_metals(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    metals = db.query(MetalInventory).filter(MetalInventory.status == "owned").order_by(MetalInventory.metal_type).all()
    result = []
    for m in metals:
        ppg = METAL_PRICES.get(m.metal_type.lower(), 0)
        val = round(m.weight_grams * m.purity * ppg, 2)
        result.append(MetalOut(id=m.id, metal_type=m.metal_type, form=m.form,
            weight_grams=m.weight_grams, purity=m.purity,
            cost_basis=m.cost_basis, current_value=val,
            purchase_date=m.purchase_date.isoformat() if m.purchase_date else None,
            storage_location=m.storage_location, notes=m.notes, status=m.status))
    return result


@app.post("/api/metals", response_model=MetalOut)
def create_metal(m: MetalCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ppg = METAL_PRICES.get(m.metal_type.lower(), 0)
    val = round(m.weight_grams * m.purity * ppg, 2)
    dt = None
    if m.purchase_date:
        try: dt = datetime.date.fromisoformat(m.purchase_date)
        except: pass
    db_m = MetalInventory(metal_type=m.metal_type, form=m.form,
        weight_grams=m.weight_grams, purity=m.purity,
        cost_basis=m.cost_basis, current_value=val,
        purchase_date=dt, storage_location=m.storage_location,
        notes=m.notes, status=m.status or "owned")
    db.add(db_m); db.commit(); db.refresh(db_m)
    return MetalOut(id=db_m.id, metal_type=db_m.metal_type, form=db_m.form,
        weight_grams=db_m.weight_grams, purity=db_m.purity,
        cost_basis=db_m.cost_basis, current_value=db_m.current_value,
        purchase_date=db_m.purchase_date.isoformat() if db_m.purchase_date else None,
        storage_location=db_m.storage_location, notes=db_m.notes, status=db_m.status)


@app.put("/api/metals/{m_id}", response_model=MetalOut)
def update_metal(m_id: int, m: MetalUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db_m = db.query(MetalInventory).get(m_id)
    if not db_m: raise HTTPException(404)
    if m.metal_type is not None: db_m.metal_type = m.metal_type
    if m.form is not None: db_m.form = m.form
    if m.weight_grams is not None: db_m.weight_grams = m.weight_grams
    if m.purity is not None: db_m.purity = m.purity
    if m.cost_basis is not None: db_m.cost_basis = m.cost_basis
    if m.purchase_date is not None:
        try: db_m.purchase_date = datetime.date.fromisoformat(m.purchase_date)
        except: pass
    if m.storage_location is not None: db_m.storage_location = m.storage_location
    if m.notes is not None: db_m.notes = m.notes
    if m.status is not None: db_m.status = m.status
    ppg = METAL_PRICES.get(db_m.metal_type.lower(), 0)
    db_m.current_value = round(db_m.weight_grams * db_m.purity * ppg, 2)
    db.commit(); db.refresh(db_m)
    return MetalOut(id=db_m.id, metal_type=db_m.metal_type, form=db_m.form,
        weight_grams=db_m.weight_grams, purity=db_m.purity,
        cost_basis=db_m.cost_basis, current_value=db_m.current_value,
        purchase_date=db_m.purchase_date.isoformat() if db_m.purchase_date else None,
        storage_location=db_m.storage_location, notes=db_m.notes, status=db_m.status)


@app.delete("/api/metals/{m_id}")
def delete_metal(m_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    m = db.query(MetalInventory).get(m_id)
    if not m: raise HTTPException(404)
    db.delete(m); db.commit()
    return {"ok": True}


@app.get("/api/metals/summary", response_model=MetalSummary)
def metal_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    metals = db.query(MetalInventory).filter(MetalInventory.status == "owned").all()
    grouped = {}
    for m in metals:
        ppg = METAL_PRICES.get(m.metal_type.lower(), 0)
        val = m.weight_grams * m.purity * ppg
        key = m.metal_type
        if key not in grouped: grouped[key] = {"weight": 0, "value": 0, "cost": 0, "count": 0}
        grouped[key]["weight"] += m.weight_grams
        grouped[key]["value"] += val
        grouped[key]["cost"] += m.cost_basis
        grouped[key]["count"] += 1
    items = []
    gw = gv = gc = 0.0
    for mt, g in sorted(grouped.items()):
        items.append(MetalSummaryItem(metal_type=mt,
            total_weight=round(g["weight"],2), total_value=round(g["value"],2),
            total_cost=round(g["cost"],2), gain_loss=round(g["value"]-g["cost"],2),
            item_count=g["count"]))
        gw += g["weight"]; gv += g["value"]; gc += g["cost"]
    return MetalSummary(items=items, grand_total_weight=round(gw,2),
        grand_total_value=round(gv,2), grand_total_cost=round(gc,2),
        grand_gain_loss=round(gv-gc,2))


# ─── Reports ───
@app.get("/api/reports/monthly", response_model=List[MonthlySummary])
def monthly_report(year: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(extract("year", Transaction.date).label("yr"),
        extract("month", Transaction.date).label("mo"),
        Transaction.type, func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).group_by("yr","mo", Transaction.type)
    if year: q = q.filter(extract("year", Transaction.date) == year)
    monthly = {}
    for yr, mo, typ, total in q.all():
        key = f"{int(yr)}-{int(mo):02d}"
        if key not in monthly: monthly[key] = MonthlySummary(month=key)
        if typ == "income": monthly[key].income = float(total)
        elif typ == "expense": monthly[key].expense = float(total)
        elif typ == "investment": monthly[key].investment = float(total)
        monthly[key].net = monthly[key].income - monthly[key].expense - monthly[key].investment
    return sorted(monthly.values(), key=lambda x: x.month, reverse=True)


@app.get("/api/reports/category-breakdown", response_model=List[CategoryBreakdown])
def category_breakdown(year: int, month: int, type: str = "expense",
    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Category.name, func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).join(Transaction,
        Transaction.category_id == Category.id).filter(
        extract("year", Transaction.date) == year,
        extract("month", Transaction.date) == month,
        Transaction.type == type).group_by(Category.name).all()
    total = sum(float(r[1]) for r in rows) or 1
    return [CategoryBreakdown(category=r[0], amount=float(r[1]),
        percentage=round(float(r[1])/total*100,1)) for r in rows]


@app.get("/api/reports/member-breakdown", response_model=List[MemberBreakdown])
def member_breakdown(year: int, month: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(FamilyMember.name, Transaction.type, func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).join(Transaction,
        Transaction.member_id == FamilyMember.id).filter(
        extract("year", Transaction.date) == year,
        extract("month", Transaction.date) == month).group_by(FamilyMember.name, Transaction.type).all()
    members = {}
    for name, typ, total in rows:
        if name not in members: members[name] = MemberBreakdown(member=name)
        if typ == "income": members[name].income = float(total)
        elif typ == "expense": members[name].expense = float(total)
        elif typ == "investment": members[name].investment = float(total)
    return list(members.values())


@app.get("/api/reports/balance-over-time")
def balance_over_time(months: int = 12, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(extract("year", Transaction.date).label("yr"),
        extract("month", Transaction.date).label("mo"),
        Transaction.type, func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).group_by("yr","mo",Transaction.type).order_by("yr","mo").all()
    running = 0.0; points = []
    for yr, mo, typ, total in rows:
        amt = float(total)
        running += amt if typ == "income" else -amt
        points.append({"month": f"{int(yr)}-{int(mo):02d}", "balance": round(running,2)})
    return points[-months:] if len(points) > months else points


@app.get("/api/reports/summary")
def quick_summary(year: int, month: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Transaction).filter(extract("year", Transaction.date) == year,
        extract("month", Transaction.date) == month)
    totals = {"income": 0, "expense": 0, "investment": 0}
    tags_set = set()
    for t in q.all():
        totals[t.type] += (t.amount_aed or t.amount)
        if t.tags:
            for tag in t.tags.split(","):
                tag = tag.strip()
                if tag: tags_set.add(tag)
    return {"month": f"{year}-{month:02d}", "income": round(totals["income"],2),
        "expense": round(totals["expense"],2), "investment": round(totals["investment"],2),
        "net": round(totals["income"]-totals["expense"]-totals["investment"],2),
        "transaction_count": q.count(), "tags": sorted(list(tags_set))}


@app.get("/api/reports/net-worth", response_model=List[NetWorthPoint])
def net_worth_over_time(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(extract("year", Transaction.date).label("yr"),
        extract("month", Transaction.date).label("mo"),
        Transaction.type, func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).group_by("yr","mo",Transaction.type).order_by("yr","mo").all()
    monthly = {}
    for yr, mo, typ, total in rows:
        key = f"{int(yr)}-{int(mo):02d}"
        if key not in monthly: monthly[key] = {"income":0,"expense":0,"investment":0}
        monthly[key][typ] += float(total)
    result = []; running = 0.0
    for key in sorted(monthly.keys()):
        m = monthly[key]; running += m["income"] - m["expense"] - m["investment"]
        result.append(NetWorthPoint(month=key, net_worth=round(running,2),
            total_income=round(m["income"],2), total_expense=round(m["expense"],2),
            total_investment=round(m["investment"],2)))
    return result


@app.get("/api/reports/portfolio", response_model=List[PortfolioHolding])
def portfolio_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Category.name, func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).join(Transaction,
        Transaction.category_id == Category.id).filter(
        Transaction.type == "investment").group_by(Category.name).all()
    if not rows: return []
    total = sum(float(r[1]) for r in rows)
    return [PortfolioHolding(category=r[0], cost_basis=round(float(r[1]),2),
        current_value=round(float(r[1]),2), gain_loss=0, gain_loss_pct=0,
        allocation_pct=round(float(r[1])/total*100,1)) for r in rows]


# ─── PDF Report ───
@app.get("/api/reports/pdf")
def generate_pdf(year: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        from fpdf import FPDF
    except ImportError:
        raise HTTPException(500, "PDF library not installed. Run: pip install fpdf2")
    pdf = FPDF(); pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 20, "Lead Vaults Finance", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 14)
    pdf.cell(0, 10, f"Annual Report {year}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    annual = db.query(Transaction.type, func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).filter(
        extract("year", Transaction.date) == year).group_by(Transaction.type).all()
    totals = {"income": 0, "expense": 0, "investment": 0}
    for typ, amt in annual:
        if typ in totals: totals[typ] = float(amt)
    net = totals["income"] - totals["expense"] - totals["investment"]
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Annual Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for label, key in [("Total Income","income"),("Total Expenses","expense"),("Total Investments","investment"),("Net","net")]:
        val = totals[key] if key != "net" else net
        pdf.cell(90, 7, f"  {label}:"); pdf.cell(0, 7, f"${val:,.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    monthly = db.query(extract("month", Transaction.date).label("mo"),
        Transaction.type, func.sum(func.coalesce(Transaction.amount_aed, Transaction.amount))).filter(
        extract("year", Transaction.date) == year).group_by("mo",Transaction.type).order_by("mo").all()
    md = {i: {"income":0.0,"expense":0.0,"investment":0.0} for i in range(1,13)}
    for mo, typ, amt in monthly:
        if typ in md[int(mo)]: md[int(mo)][typ] = float(amt)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Monthly Breakdown", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 8)
    cols = ["Month","Income","Expenses","Investments","Net"]
    cw = [30,38,38,38,38]
    for i, c in enumerate(cols): pdf.cell(cw[i], 6, c, border=1)
    pdf.ln(); pdf.set_font("Helvetica", "", 8)
    mn = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    for mo in range(1,13):
        d = md[mo]; m_net = d["income"] - d["expense"] - d["investment"]
        vals = [mn[mo], d["income"], d["expense"], d["investment"], m_net]
        for i, v in enumerate(vals):
            text = f"${v:,.2f}" if isinstance(v, float) else v
            pdf.cell(cw[i], 6, text, border=1)
        pdf.ln()
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Metal Holdings", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 8)
    for h in ["Type","Weight (g)","Cost Basis","Current Value","Gain/Loss"]:
        pdf.cell(36, 6, h, border=1)
    pdf.ln(); pdf.set_font("Helvetica", "", 8)
    for m in db.query(MetalInventory).filter(MetalInventory.status=="owned").all():
        ppg = METAL_PRICES.get(m.metal_type.lower(),0)
        val = round(m.weight_grams * m.purity * ppg, 2)
        gain = val - m.cost_basis
        for v in [m.metal_type.title(), f"{m.weight_grams:.1f}", f"${m.cost_basis:,.2f}", f"${val:,.2f}", f"${gain:,.2f}"]:
            pdf.cell(36, 6, v, border=1)
        pdf.ln()
    from io import BytesIO
    buf = BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=lead-vaults-report-{year}.pdf"})

# ─── Serve Frontend ───
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
