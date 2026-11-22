from fastapi import APIRouter

from ledger.deps import DbSession
from ledger.schemas import CreatedCount
from ledger.services import demo

router = APIRouter(tags=["デモ"])


@router.post("/demo-data", status_code=201, response_model=CreatedCount)
def load_demo_data(db: DbSession):
    return CreatedCount(created=demo.load_demo_data(db))
