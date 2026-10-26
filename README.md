# SpendWise

**Understand where your money goes.** SpendWise is a personal finance dashboard that turns bank statement CSVs into searchable transactions, monthly spending insights, budgets, and recurring charge estimates.

> SpendWise analyzes statements that you choose to import. It does not connect to your bank or provide financial advice.

## What you can do

- Import CSV statements and skip duplicate transactions automatically.
- Review monthly income, expenses, net cash flow, and spending by category.
- Search and filter transaction history, then download a monthly CSV report.
- Set monthly category budgets and see remaining or over-budget amounts.
- Spot possible subscriptions and unusually large expenses from transaction history.

## Preview

SpendWise runs locally in your browser with a React dashboard and a FastAPI service backed by PostgreSQL.

## Start with Docker

**You need:** Docker Desktop or Docker Engine with the Docker Compose plugin.

```bash
git clone https://github.com/ArnavPal6805/Spendwise.git
cd Spendwise
docker compose up --build
```

Open the app and API documentation:

| Service | Address |
| --- | --- |
| SpendWise dashboard | http://localhost:5173 |
| API documentation | http://localhost:8000/docs |
| API health check | http://localhost:8000/api/health |

Stop the app with `Ctrl+C`, or run `docker compose down`. PostgreSQL data is stored in the `spendwise_db` volume and remains between restarts. To remove the database and its data, run `docker compose down -v`.

## Import a statement

1. Export a statement as CSV from your bank or card provider. SpendWise never asks for banking passwords, PINs, or one-time codes.
2. In the dashboard, select **Import statement** and choose the CSV file.
3. Review the import summary and check the transactions in your dashboard.

SpendWise recognizes common date, description, and amount headers, including `Date`, `Transaction Date`, `Description`, `Narration`, `Amount`, and paired `Debit` / `Credit` columns. Invalid rows are reported, and duplicate rows are skipped. CSV and TXT files up to 15 MB are accepted; export Excel statements as CSV first.

**Amounts:** expenses and debits are positive; income, credits, refunds, and deposits are negative. Ambiguous dates are interpreted day-first. Values display with an INR symbol, so use INR statements unless you adapt the currency formatter.

## Features and API

| Capability | Endpoint |
| --- | --- |
| Import transactions | `POST /api/import` |
| List, search, and filter transactions | `GET /api/transactions` |
| Monthly overview | `GET /api/analytics/overview?month=YYYY-MM` |
| Detected subscriptions | `GET /api/subscriptions` |
| List or create budgets | `GET /api/budgets`, `POST /api/budgets` |
| Delete a budget | `DELETE /api/budgets/{id}` |
| Download monthly CSV report | `GET /api/reports/monthly.csv?month=YYYY-MM` |

The interactive API schema is available at http://localhost:8000/docs.

## Development

**Requirements:** Python 3.12+, Node.js 22+, and PostgreSQL. Set `DATABASE_URL` to a SQLAlchemy PostgreSQL URL, for example:

```text
postgresql+psycopg://USER:PASSWORD@localhost:5432/spendwise
```

Install and run the backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In another terminal, install and run the frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend uses `http://localhost:8000/api` by default. Set `VITE_API_URL` to use a different API address.

## Technology

- **Frontend:** React, TypeScript, Vite, Recharts, Lucide
- **Backend:** Python, FastAPI, SQLAlchemy, pandas
- **Database:** PostgreSQL
- **Local deployment:** Docker Compose

## How insights work

- Categories are assigned using merchant keyword rules; unmatched transactions are **Uncategorized**.
- Subscription detection looks for recognizable merchants with repeated transactions and a likely weekly, monthly, or annual cadence.
- Unusual spending is flagged using a category's historical average and requires at least five earlier transactions in that category.

These are heuristics: results can miss real subscriptions or flag recurring purchases and unusual transactions incorrectly.

## Privacy and limitations

SpendWise imports transaction data only from files you select. The initial version has no sign-in or multi-user isolation, so keep it local and do not expose it publicly with personal financial data. Before a public deployment, add authentication, authorization, appropriate data protection, and operational safeguards. Database tables are created at API startup; production use should also add migrations and stronger deployment controls.
