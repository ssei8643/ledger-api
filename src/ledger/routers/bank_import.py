from fastapi import APIRouter

from ledger.deps import DbSession
from ledger.schemas import BankDraft, BankImportCommit, BankImportRequest, CreatedCount
from ledger.services import bank_import

router = APIRouter(tags=["銀行明細の取り込み"])


@router.post("/bank-import/preview", response_model=list[BankDraft])
def preview_bank_import(payload: BankImportRequest, db: DbSession):
    return bank_import.preview(db, payload.csv_text)


@router.post("/bank-import", status_code=201, response_model=CreatedCount)
def commit_bank_import(payload: BankImportCommit, db: DbSession):
    return CreatedCount(created=bank_import.commit(db, payload.drafts))
