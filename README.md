# Lead Vaults Finance

**Simple, shared family finance tracking for couples.**

Track income, expenses, and investments together in one place. Zero setup, zero maintenance, zero learning curve.

## Tech Stack

- **Backend**: Python FastAPI + SQLAlchemy + SQLite
- **Frontend**: Vanilla HTML/CSS/JS (single file, no framework)
- **Auth**: JWT tokens (bcrypt password hashing)
- **Charts**: Chart.js

## Quick Start

```bash
pip install -r backend/requirements.txt
cd backend && python main.py
```

Opens on `http://localhost:8000`

## Features

- 📊 Dashboard with summary cards, balance trend, expense pie, member breakdown
- ➕ Add Income / Expense / Investment transactions with dynamic category filtering
- 📋 History with year/month/type/member filters, edit, and delete
- 📈 Reports with income vs expense, expense breakdown, and investment breakdown charts
- ⚙️ Settings with password change
- 👥 Built-in family member support (Suren + Partner)
- 🌙 Dark mode
- 🔐 JWT authentication

## Comparison

**vs Firefly III**: Lead Vaults has built-in family sharing + investment tracking. Firefly III is single-user only.
**vs Akaunting**: Lead Vaults is for personal/family use, not business accounting. 1,700 LOC vs 180,000+.

## License

MIT
