import csv, io, re
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional
import pandas as pd
from fastapi import FastAPI, Depends, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, desc
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import Transaction, Budget, Subscription
from .schemas import TransactionOut, BudgetIn, BudgetOut
from .logic import categorize, normalize_merchant, fingerprint, is_subscription_merchant

Base.metadata.create_all(bind=engine)
app = FastAPI(title="SpendWise API", version="1.0.0", description="Personal expense analytics using user-imported transaction data.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
def health(): return {"status": "ok", "database": "connected"}

DATE_KEYS = ["date", "transaction date", "posted date", "posting date", "value date"]
DESC_KEYS = ["description", "narration", "details", "merchant", "transaction details", "particulars", "name"]
AMOUNT_KEYS = ["amount", "transaction amount", "debit/credit", "value"]
DEBIT_KEYS = ["debit", "withdrawal", "withdrawals", "money out"]
CREDIT_KEYS = ["credit", "deposit", "deposits", "money in"]
ACCOUNT_KEYS = ["account", "account name", "account number", "card"]

def keymap(headers): return {re.sub(r"[^a-z0-9/ ]", "", str(h).lower()).strip(): h for h in headers}
def choose(keys, candidates):
    for k in candidates:
        if k in keys: return keys[k]
    for normalized, original in keys.items():
        if any(c in normalized for c in candidates): return original
    return None

def parse_date(value):
    if pd.isna(value) or not str(value).strip():
        raise ValueError("missing date")
    text = str(value).strip()
    # ISO dates (YYYY-MM-DD) must be parsed year-first; dayfirst=True misreads
    # values such as 2026-09-01 as 9 January 2026.
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}(?:[ T].*)?$", text):
        parsed = pd.to_datetime(text, errors="coerce", yearfirst=True, dayfirst=False)
    else:
        # For non-ISO bank exports, support common day-first formats.
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        raise ValueError(f"invalid date: {value}")
    return parsed.date()

def parse_amount(row, amount_col, debit_col, credit_col):
    def number(v):
        s = str(v or "").strip().replace(",", "").replace("₹", "").replace("$", "").replace("INR", "")
        if s.lower() in ("", "nan", "none", "-", "—"): return Decimal("0")
        neg = s.startswith("(") and s.endswith(")")
        s = s.strip("() ")
        val = Decimal(s)
        return -val if neg else val
    if debit_col and credit_col:
        debit, credit = number(row.get(debit_col)), number(row.get(credit_col))
        return debit if debit != 0 else -credit
    if not amount_col: raise ValueError("No amount column found. Use Amount or Debit and Credit columns.")
    amount = number(row.get(amount_col))
    # If a type/direction column exists, respect common debit/credit labels.
    direction = " ".join(str(v).lower() for k,v in row.items() if any(t in str(k).lower() for t in ["type", "dr/cr", "transaction type"]))
    if any(x in direction for x in ["credit", "deposit", "cr"]): return -abs(amount)
    if any(x in direction for x in ["debit", "withdrawal", "dr"]): return abs(amount)
    return amount

@app.post("/api/import")
async def import_transactions(file: UploadFile = File(...), account: str = Query("Imported statement"), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith((".csv", ".txt")):
        raise HTTPException(400, "Upload a CSV statement. XLSX is not supported yet; export it as CSV first.")
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024: raise HTTPException(413, "File exceeds 15 MB limit.")
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, sep=None, engine="python", encoding_errors="replace")
    except Exception as e: raise HTTPException(400, f"Could not read CSV: {e}")
    if df.empty: raise HTTPException(400, "CSV has no transaction rows.")
    keys = keymap(df.columns)
    date_col, desc_col = choose(keys, DATE_KEYS), choose(keys, DESC_KEYS)
    amount_col = choose(keys, AMOUNT_KEYS)
    debit_col, credit_col = choose(keys, DEBIT_KEYS), choose(keys, CREDIT_KEYS)
    account_col = choose(keys, ACCOUNT_KEYS)
    if not date_col or not desc_col or (not amount_col and not (debit_col and credit_col)):
        raise HTTPException(400, "Could not identify required columns. Need Date, Description/Narration, and Amount OR Debit + Credit. Detected columns: " + ", ".join(map(str, df.columns)))
    imported, skipped, errors = 0, 0, []
    # Track fingerprints within this upload as well as those already persisted.
    # Without this set, repeated rows in one CSV batch can violate the unique
    # database constraint because pending db.add() rows are not yet queryable.
    seen_fingerprints = set()
    for idx, row in df.iterrows():
        try:
            tx_date = parse_date(row[date_col])
            description = str(row[desc_col]).strip()
            if not description:
                raise ValueError("missing description")
            amount = parse_amount(row, amount_col, debit_col, credit_col).quantize(Decimal("0.01"))
            if amount == 0:
                skipped += 1
                continue
            account_name = str(row[account_col]).strip() if account_col and str(row[account_col]).strip() else account
            fp = fingerprint(tx_date, description, amount, account_name)
            if fp in seen_fingerprints or db.query(Transaction).filter(Transaction.fingerprint == fp).first():
                skipped += 1
                continue
            seen_fingerprints.add(fp)
            merchant = normalize_merchant(description)
            tx = Transaction(transaction_date=tx_date, description=description[:500], merchant=merchant, amount=amount, category=categorize(description, amount), account=account_name[:120], source_file=file.filename[:255], fingerprint=fp)
            db.add(tx)
            imported += 1
        except (ValueError, InvalidOperation, TypeError) as e:
            if len(errors) < 10:
                errors.append({"row": int(idx)+2, "error": str(e)})
    try: db.commit()
    except Exception as e: db.rollback(); raise HTTPException(500, f"Database import failed: {e}")
    detect_duplicates(db)
    sync_subscriptions(db)
    return {"filename": file.filename, "rows_seen": len(df), "imported": imported, "skipped_or_duplicate": skipped, "errors": errors, "message": "Imported rows are real records from the uploaded statement; no sample transactions were generated."}

def detect_duplicates(db: Session):
    # Exact duplicates are prevented by fingerprint. This flags likely duplicates with same date/amount/merchant across accounts/descriptions.
    db.query(Transaction).update({Transaction.is_duplicate_candidate: False}, synchronize_session=False)
    rows = db.query(Transaction).all(); groups = defaultdict(list)
    for t in rows: groups[(t.transaction_date, round(float(t.amount),2), re.sub(r'\W','',t.merchant.lower()))].append(t)
    for group in groups.values():
        if len(group) > 1:
            for t in group: t.is_duplicate_candidate = True
    db.commit()

def sync_subscriptions(db: Session):
    rows = db.query(Transaction).filter(Transaction.amount > 0).order_by(Transaction.transaction_date).all()
    groups = defaultdict(list)
    for t in rows:
        if is_subscription_merchant(t.merchant) or is_subscription_merchant(t.description): groups[t.merchant.lower()].append(t)
    for merchant, ts in groups.items():
        if len(ts) < 2: continue
        dates = sorted(t.transaction_date for t in ts)
        gaps = [(dates[i]-dates[i-1]).days for i in range(1,len(dates))]
        monthly = sum(20 <= g <= 40 for g in gaps); annual = sum(330 <= g <= 400 for g in gaps); weekly = sum(5 <= g <= 9 for g in gaps)
        cadence = "monthly" if monthly >= max(weekly, annual) else "weekly" if weekly > annual else "annual" if annual else None
        if not cadence: continue
        recent = ts[-1]; avg = sum(float(t.amount) for t in ts)/len(ts)
        sub = db.query(Subscription).filter(func.lower(Subscription.merchant)==merchant).first()
        if not sub: sub = Subscription(merchant=recent.merchant, typical_amount=round(avg,2), cadence=cadence, last_charge=recent.transaction_date, occurrence_count=len(ts), active=True); db.add(sub)
        else: sub.typical_amount=round(avg,2); sub.cadence=cadence; sub.last_charge=recent.transaction_date; sub.occurrence_count=len(ts); sub.active=True
    db.commit()

@app.get("/api/transactions", response_model=list[TransactionOut])
def list_transactions(search: Optional[str]=None, category: Optional[str]=None, start_date: Optional[date]=None, end_date: Optional[date]=None, min_amount: Optional[float]=None, max_amount: Optional[float]=None, duplicates_only: bool=False, limit: int=Query(100, ge=1, le=500), offset: int=Query(0, ge=0), db: Session=Depends(get_db)):
    q=db.query(Transaction)
    if search: q=q.filter(or_(Transaction.description.ilike(f"%{search}%"), Transaction.merchant.ilike(f"%{search}%")))
    if category: q=q.filter(Transaction.category==category)
    if start_date: q=q.filter(Transaction.transaction_date>=start_date)
    if end_date: q=q.filter(Transaction.transaction_date<=end_date)
    if min_amount is not None: q=q.filter(Transaction.amount>=min_amount)
    if max_amount is not None: q=q.filter(Transaction.amount<=max_amount)
    if duplicates_only: q=q.filter(Transaction.is_duplicate_candidate.is_(True))
    return q.order_by(desc(Transaction.transaction_date), desc(Transaction.id)).offset(offset).limit(limit).all()

@app.get("/api/transactions/count")
def transaction_count(db: Session=Depends(get_db)): return {"count": db.query(func.count(Transaction.id)).scalar() or 0}

@app.get("/api/analytics/overview")
def overview(month: Optional[str]=None, db: Session=Depends(get_db)):
    month = month or date.today().strftime("%Y-%m")
    try: start=date.fromisoformat(month+"-01")
    except ValueError: raise HTTPException(400,"month must be YYYY-MM")
    end=date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
    txs=db.query(Transaction).filter(Transaction.transaction_date>=start,Transaction.transaction_date<end).all()
    expenses=sum(float(t.amount) for t in txs if float(t.amount)>0); income=sum(-float(t.amount) for t in txs if float(t.amount)<0)
    categories=defaultdict(float); days=defaultdict(float)
    for t in txs:
        if float(t.amount)>0: categories[t.category]+=float(t.amount); days[t.transaction_date.day]+=float(t.amount)
    prev_start=date(start.year-1,12,1) if start.month==1 else date(start.year,start.month-1,1)
    prev_txs=db.query(Transaction).filter(Transaction.transaction_date>=prev_start,Transaction.transaction_date<start,Transaction.amount>0).all()
    prev_expenses=sum(float(t.amount) for t in prev_txs)
    budgets=db.query(Budget).filter(Budget.month==month).all()
    budget_data=[]
    for b in budgets: budget_data.append({"category":b.category,"limit":float(b.limit_amount),"spent":round(categories.get(b.category,0),2),"remaining":round(float(b.limit_amount)-categories.get(b.category,0),2)})
    unusual=[]
    history=db.query(Transaction).filter(Transaction.amount>0,Transaction.transaction_date<start).all()
    bycat=defaultdict(list)
    for t in history: bycat[t.category].append(float(t.amount))
    for t in txs:
        amount=float(t.amount); hist=bycat.get(t.category,[])
        if amount>0 and len(hist)>=5:
            avg=sum(hist)/len(hist)
            if amount > max(avg*3, avg+1000): unusual.append({"id":t.id,"date":t.transaction_date.isoformat(),"merchant":t.merchant,"amount":round(amount,2),"category":t.category,"historical_average":round(avg,2)})
    return {"month":month,"currency":"statement currency (amounts are not converted)","income":round(income,2),"expenses":round(expenses,2),"net":round(income-expenses,2),"previous_month_expenses":round(prev_expenses,2),"expense_change_percent":round((expenses-prev_expenses)/prev_expenses*100,1) if prev_expenses else None,"transaction_count":len(txs),"category_spend":[{"category":k,"amount":round(v,2)} for k,v in sorted(categories.items(),key=lambda x:-x[1])],"daily_spend":[{"day":k,"amount":round(v,2)} for k,v in sorted(days.items())],"budgets":budget_data,"unusual_transactions":unusual,"duplicate_candidates":db.query(func.count(Transaction.id)).filter(Transaction.is_duplicate_candidate.is_(True)).scalar() or 0}

@app.get("/api/budgets", response_model=list[BudgetOut])
def get_budgets(month: Optional[str]=None, db: Session=Depends(get_db)):
    q=db.query(Budget)
    if month: q=q.filter(Budget.month==month)
    return q.order_by(Budget.month.desc(),Budget.category).all()

@app.post("/api/budgets", response_model=BudgetOut)
def set_budget(payload: BudgetIn, db: Session=Depends(get_db)):
    b=db.query(Budget).filter(Budget.month==payload.month,Budget.category==payload.category).first()
    if b: b.limit_amount=payload.limit_amount
    else: b=Budget(**payload.model_dump()); db.add(b)
    db.commit(); db.refresh(b); return b

@app.delete("/api/budgets/{budget_id}")
def delete_budget(budget_id:int, db:Session=Depends(get_db)):
    b=db.get(Budget,budget_id)
    if not b: raise HTTPException(404,"Budget not found")
    db.delete(b); db.commit(); return {"deleted":True}

@app.get("/api/subscriptions")
def subscriptions(db:Session=Depends(get_db)):
    return [{"id":s.id,"merchant":s.merchant,"typical_amount":float(s.typical_amount),"cadence":s.cadence,"last_charge":s.last_charge.isoformat(),"occurrence_count":s.occurrence_count,"active":s.active} for s in db.query(Subscription).order_by(Subscription.merchant).all()]

@app.get("/api/reports/monthly.csv")
def monthly_report(month: str=Query(..., pattern=r"^\d{4}-\d{2}$"), db:Session=Depends(get_db)):
    try: start=date.fromisoformat(month+"-01")
    except ValueError: raise HTTPException(400,"Invalid month")
    end=date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
    txs=db.query(Transaction).filter(Transaction.transaction_date>=start,Transaction.transaction_date<end).order_by(Transaction.transaction_date).all()
    output=io.StringIO(); writer=csv.writer(output); writer.writerow(["Date","Description","Merchant","Amount","Category","Account","Duplicate candidate"])
    for t in txs: writer.writerow([t.transaction_date.isoformat(),t.description,t.merchant,str(t.amount),t.category,t.account,"Yes" if t.is_duplicate_candidate else "No"])
    from fastapi.responses import StreamingResponse
    return StreamingResponse(iter([output.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename=spendwise-{month}.csv"})
