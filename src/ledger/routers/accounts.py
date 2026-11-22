from fastapi import APIRouter

from ledger.deps import DbSession
from ledger.schemas import AccountOut, LedgerRow
from ledger.services import accounts, reports

router = APIRouter(tags=["勘定科目"])


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: DbSession):
    return accounts.list_accounts(db)


@router.get("/accounts/{account_name}/ledger", response_model=list[LedgerRow])
def get_ledger(account_name: str, db: DbSession):
    return reports.account_ledger(db, account_name)
