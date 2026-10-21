from datetime import date
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator

app = FastAPI()


class JournalLine(BaseModel):
    account: str
    side: Literal["debit", "credit"]
    amount: int = Field(gt=0)


class JournalEntryCreate(BaseModel):
    entry_date: date
    description: str
    lines: list[JournalLine] = Field(min_length=2)

    @model_validator(mode="after")
    def check_balanced(self):
        debit = sum(l.amount for l in self.lines if l.side == "debit")
        credit = sum(l.amount for l in self.lines if l.side == "credit")
        if debit != credit:
            raise ValueError(f"借方合計 {debit} と貸方合計 {credit} が一致しません")
        return self


journal_entries: list[JournalEntryCreate] = []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/journal-entries", status_code=201)
def create_journal_entry(entry: JournalEntryCreate):
    journal_entries.append(entry)
    return entry


@app.get("/journal-entries")
def list_journal_entries():
    return journal_entries