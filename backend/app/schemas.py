from datetime import date
from pydantic import BaseModel, ConfigDict, Field

class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transaction_date: date
    description: str
    merchant: str
    amount: float
    category: str
    account: str
    source_file: str
    is_duplicate_candidate: bool

class BudgetIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    category: str
    limit_amount: float = Field(gt=0)

class BudgetOut(BudgetIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
