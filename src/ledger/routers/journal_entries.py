from fastapi import APIRouter

from ledger.deps import DbSession
from ledger.schemas import JournalEntryCreate, JournalEntryOut, JournalTemplate, ReverseRequest
from ledger.services import journal
from ledger.services.templates import TEMPLATES

router = APIRouter(tags=["仕訳"])


@router.post("/journal-entries", status_code=201, response_model=JournalEntryOut)
def create_journal_entry(payload: JournalEntryCreate, db: DbSession):
    return journal.create_entry(db, payload)


@router.get("/journal-entries", response_model=list[JournalEntryOut])
def list_journal_entries(db: DbSession):
    return journal.list_entries(db)


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryOut)
def get_journal_entry(entry_id: int, db: DbSession):
    return journal.get_entry(db, entry_id)


@router.post("/journal-entries/{entry_id}/reverse", status_code=201, response_model=JournalEntryOut)
def reverse_journal_entry(entry_id: int, payload: ReverseRequest, db: DbSession):
    return journal.reverse_entry(db, entry_id, payload)


@router.get("/templates", response_model=list[JournalTemplate])
def list_templates():
    return TEMPLATES
