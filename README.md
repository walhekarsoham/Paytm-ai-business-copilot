# Paytm Merchant Growth Copilot

Grocery merchant workspace built with React, Vite, TypeScript, Tailwind CSS, Recharts, and Lucide. The frontend uses an authenticated FastAPI API and PostgreSQL database (Neon-compatible) for merchant, dashboard, sales, product, inventory, and campaign data.

## Start the backend

See [backend/README.md](backend/README.md) for Neon configuration, migrations, seed data, security notes, and API examples.

```powershell
Set-Location .\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Add your Neon DATABASE_URL and a private JWT_SECRET_KEY to backend/.env.
python -m alembic upgrade head
python seed.py
python -m uvicorn app.main:app --reload --port 8000
```

The interactive API documentation is at `http://localhost:8000/docs`.

## Start the frontend

In another terminal, from the `merchant-copilot` project root:

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

`VITE_API_BASE_URL` is a public API URL, not a credential. Database URLs and JWT signing keys belong only in `backend/.env`; neither is read by Vite.

## Verify

```powershell
Set-Location .\backend
python -m pytest
```

Tests use SQLite and do not need Neon credentials. They cover authentication, merchant data isolation, and atomic sale/stock behavior.

