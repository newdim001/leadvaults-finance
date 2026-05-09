from __future__ import annotations
import os
import datetime
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import func, extract
from sqlalchemy.orm import Session
from jose import jwt, JWTError

# Password hashing - use bcrypt directly (compatible with bcrypt 5.x)
import bcrypt as _bcrypt
class _PwdCtx:
    def hash(self, secret): return _bcrypt.hashpw(secret.encode(), _bcrypt.gensalt()).decode()
    def verify(self, secret, hash): return _bcrypt.checkpw(secret.encode(), hash.encode())
pwd_ctx = _PwdCtx()

from database import engine, Base, get_db, SessionLocal
from models import User, FamilyMember, Category, Transaction
from schemas import (
    LoginRequest, TokenResponse, ChangePasswordRequest,
    CategoryCreate, CategoryOut,
    MemberCreate, MemberOut,
    TransactionCreate, TransactionOut,
    MonthlySummary, CategoryBreakdown, MemberBreakdown,
)

# ─── Config ───
SECRET_KEY = os.environ.get("FINANCE_SECRET", "change-me-in-production-v3")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 90
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

Base.metadata.create_all(bind=engine)
security = HTTPBearer(auto_error=False)

app = FastAPI(title="Family Finance")


# ─── Auth Helpers ───
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


# ─── Seed Defaults ───
def seed_data():
    db = SessionLocal()
    try:
        # Seed admin user
        if db.query(User).count() == 0:
            db.add(User(
                username="admin",
                password_hash=pwd_ctx.hash("admin123"),
            ))
        # Seed family members
        if db.query(FamilyMember).count() == 0:
            db.add_all([
                FamilyMember(name="Suren"),
                FamilyMember(name="Partner"),
            ])
        # Seed categories
        if db.query(Category).count() == 0:
            db.add_all([
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
            ])
        db.commit()
    finally:
        db.close()

seed_data()


# ─── Auth Routes ───
@app.post("/api/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not pwd_ctx.verify(req.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    return TokenResponse(token=create_token(user.username), username=user.username)


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
    return {"ok": True, "username": user.username}


# ─── Categories ───
@app.get("/api/categories", response_model=list[CategoryOut])
def list_categories(type: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Category)
    if type:
        q = q.filter(Category.type == type)
    return q.order_by(Category.name).all()


@app.post("/api/categories", response_model=CategoryOut)
def create_category(cat: CategoryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = db.query(Category).filter(Category.name == cat.name, Category.type == cat.type).first()
    if existing:
        raise HTTPException(400, "Category already exists")
    db_cat = Category(name=cat.name, type=cat.type)
    db.add(db_cat)
    db.commit()
    db.refresh(db_cat)
    return db_cat


@app.delete("/api/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cat = db.query(Category).get(cat_id)
    if not cat:
        raise HTTPException(404)
    if db.query(Transaction).filter(Transaction.category_id == cat_id).count():
        raise HTTPException(400, "Category has transactions, reassign first")
    db.delete(cat)
    db.commit()
    return {"ok": True}


# ─── Family Members ───
@app.get("/api/members", response_model=list[MemberOut])
def list_members(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(FamilyMember).order_by(FamilyMember.name).all()


@app.post("/api/members", response_model=MemberOut)
def create_member(m: MemberCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = db.query(FamilyMember).filter(FamilyMember.name == m.name).first()
    if existing:
        raise HTTPException(400, "Member already exists")
    db_m = FamilyMember(name=m.name)
    db.add(db_m)
    db.commit()
    db.refresh(db_m)
    return db_m


@app.delete("/api/members/{member_id}")
def delete_member(member_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    m = db.query(FamilyMember).get(member_id)
    if not m:
        raise HTTPException(404)
    if db.query(Transaction).filter(Transaction.member_id == member_id).count():
        raise HTTPException(400, "Member has transactions")
    db.delete(m)
    db.commit()
    return {"ok": True}


# ─── Transactions ───
@app.get("/api/transactions", response_model=list[TransactionOut])
def list_transactions(
    year: Optional[int] = None,
    month: Optional[int] = None,
    type: Optional[str] = None,
    member_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Transaction)
    if year:
        q = q.filter(extract("year", Transaction.date) == year)
    if month:
        q = q.filter(extract("month", Transaction.date) == month)
    if type:
        q = q.filter(Transaction.type == type)
    if member_id:
        q = q.filter(Transaction.member_id == member_id)
    q = q.order_by(Transaction.date.desc(), Transaction.id.desc())
    results = q.offset(offset).limit(limit).all()
    return [
        TransactionOut(
            id=t.id, date=t.date.isoformat(), amount=t.amount, type=t.type,
            description=t.description, category_id=t.category_id,
            category_name=t.category.name, member_id=t.member_id,
            member_name=t.member.name,
        ) for t in results
    ]


@app.post("/api/transactions", response_model=TransactionOut)
def create_transaction(t: TransactionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cat = db.query(Category).get(t.category_id)
    if not cat: raise HTTPException(400, "Category not found")
    mem = db.query(FamilyMember).get(t.member_id)
    if not mem: raise HTTPException(400, "Member not found")
    try:
        dt = datetime.date.fromisoformat(t.date)
    except ValueError:
        raise HTTPException(400, "Invalid date format")
    db_t = Transaction(date=dt, amount=t.amount, type=t.type, description=t.description,
                       category_id=t.category_id, member_id=t.member_id)
    db.add(db_t)
    db.commit()
    db.refresh(db_t)
    return TransactionOut(id=db_t.id, date=db_t.date.isoformat(), amount=db_t.amount,
                          type=db_t.type, description=db_t.description,
                          category_id=db_t.category_id, category_name=cat.name,
                          member_id=db_t.member_id, member_name=mem.name)


@app.put("/api/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(tx_id: int, t: TransactionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db_t = db.query(Transaction).get(tx_id)
    if not db_t: raise HTTPException(404)
    cat = db.query(Category).get(t.category_id)
    if not cat: raise HTTPException(400, "Category not found")
    mem = db.query(FamilyMember).get(t.member_id)
    if not mem: raise HTTPException(400, "Member not found")
    try:
        dt = datetime.date.fromisoformat(t.date)
    except ValueError:
        raise HTTPException(400, "Invalid date")
    db_t.date = dt; db_t.amount = t.amount; db_t.type = t.type
    db_t.description = t.description; db_t.category_id = t.category_id; db_t.member_id = t.member_id
    db.commit()
    db.refresh(db_t)
    return TransactionOut(id=db_t.id, date=db_t.date.isoformat(), amount=db_t.amount,
                          type=db_t.type, description=db_t.description,
                          category_id=db_t.category_id, category_name=cat.name,
                          member_id=db_t.member_id, member_name=mem.name)


@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.query(Transaction).get(tx_id)
    if not t: raise HTTPException(404)
    db.delete(t); db.commit()
    return {"ok": True}


# ─── Reports ───
@app.get("/api/reports/monthly", response_model=list[MonthlySummary])
def monthly_report(year: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(extract("year", Transaction.date).label("yr"),
                 extract("month", Transaction.date).label("mo"),
                 Transaction.type, func.sum(Transaction.amount)
                 ).group_by("yr", "mo", Transaction.type)
    if year: q = q.filter(extract("year", Transaction.date) == year)
    rows = q.all()
    monthly = {}
    for yr, mo, typ, total in rows:
        key = f"{int(yr)}-{int(mo):02d}"
        if key not in monthly:
            monthly[key] = MonthlySummary(month=key)
        if typ == "income": monthly[key].income = float(total)
        elif typ == "expense": monthly[key].expense = float(total)
        elif typ == "investment": monthly[key].investment = float(total)
        monthly[key].net = monthly[key].income - monthly[key].expense - monthly[key].investment
    return sorted(monthly.values(), key=lambda x: x.month, reverse=True)


@app.get("/api/reports/category-breakdown", response_model=list[CategoryBreakdown])
def category_breakdown(year: int, month: int, type: str = "expense",
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Category.name, func.sum(Transaction.amount)) \
        .join(Transaction, Transaction.category_id == Category.id) \
        .filter(extract("year", Transaction.date) == year,
                extract("month", Transaction.date) == month,
                Transaction.type == type) \
        .group_by(Category.name).all()
    total = sum(float(r[1]) for r in rows) or 1
    return [CategoryBreakdown(category=r[0], amount=float(r[1]),
                              percentage=round(float(r[1]) / total * 100, 1)) for r in rows]


@app.get("/api/reports/member-breakdown", response_model=list[MemberBreakdown])
def member_breakdown(year: int, month: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    rows = db.query(FamilyMember.name, Transaction.type, func.sum(Transaction.amount)) \
        .join(Transaction, Transaction.member_id == FamilyMember.id) \
        .filter(extract("year", Transaction.date) == year,
                extract("month", Transaction.date) == month) \
        .group_by(FamilyMember.name, Transaction.type).all()
    members = {}
    for name, typ, total in rows:
        if name not in members:
            members[name] = MemberBreakdown(member=name)
        if typ == "income": members[name].income = float(total)
        elif typ == "expense": members[name].expense = float(total)
        elif typ == "investment": members[name].investment = float(total)
    return list(members.values())


@app.get("/api/reports/balance-over-time")
def balance_over_time(months: int = 12, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    rows = db.query(extract("year", Transaction.date).label("yr"),
                    extract("month", Transaction.date).label("mo"),
                    Transaction.type, func.sum(Transaction.amount)) \
        .group_by("yr", "mo", Transaction.type).order_by("yr", "mo").all()
    running = 0.0; points = []
    for yr, mo, typ, total in rows:
        amt = float(total)
        if typ == "income": running += amt
        else: running -= amt
        points.append({"month": f"{int(yr)}-{int(mo):02d}", "balance": round(running, 2)})
    return points[-months:] if len(points) > months else points


@app.get("/api/reports/summary")
def quick_summary(year: int, month: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    q = db.query(Transaction).filter(
        extract("year", Transaction.date) == year,
        extract("month", Transaction.date) == month)
    totals = {"income": 0, "expense": 0, "investment": 0}
    for t in q.all(): totals[t.type] += t.amount
    return {
        "month": f"{year}-{month:02d}",
        "income": round(totals["income"], 2),
        "expense": round(totals["expense"], 2),
        "investment": round(totals["investment"], 2),
        "net": round(totals["income"] - totals["expense"] - totals["investment"], 2),
        "transaction_count": q.count(),
    }


# ─── Serve Frontend ───
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
