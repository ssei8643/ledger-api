"""銀行明細CSVの取り込み（科目の推測・プレビュー・登録）"""

import hashlib
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ledger.ai_suggest import suggest_accounts_with_ai
from ledger.bank_csv import BankCsvError, parse_bank_csv
from ledger.errors import ConflictError, RuleViolationError
from ledger.models import Account, JournalEntry, JournalLine
from ledger.schemas import BankDraft
from ledger.services.accounts import ensure_accounts_exist

BANK_ACCOUNT = "普通預金"

# 摘要に含まれるキーワードから勘定科目を推測するルール
OUT_RULES = [
    ("手数料", "支払手数料"),
    # 銀行の半角カナでは小さい「ョ」が使えず「ﾃｽｳﾘﾖｳ」と書かれることがある
    ("テスウリヨウ", "支払手数料"),
    ("テスウリョウ", "支払手数料"),
    ("ドコモ", "通信費"),
    ("ソフトバンク", "通信費"),
    ("NTT", "通信費"),
    ("JR", "旅費交通費"),
    ("SUICA", "旅費交通費"),
    ("AMAZON", "消耗品費"),
    ("アマゾン", "消耗品費"),
    ("ATM", "事業主貸"),
]
# 同じキーワードでも、入金か出金かで科目が変わる（例：ATMの出金は事業主貸、入金は事業主借）
IN_RULES = [
    ("フリコミ", "売掛金"),
    ("振込", "売掛金"),
    ("ATM", "事業主借"),
]


def suggest_account(description: str, direction: str) -> str | None:
    # 半角カナ・全角英数字を揃えてから比較する（例：ﾌﾘｺﾐ → フリコミ）
    text = unicodedata.normalize("NFKC", description).upper()
    rules = OUT_RULES if direction == "out" else IN_RULES
    for keyword, account in rules:
        if keyword in text:
            return account
    return None


def preview(db: Session, csv_text: str) -> list[BankDraft]:
    """CSVを読み取り、科目を推測した登録前の下書きを返す（まだ保存しない）"""
    # 銀行ごとの列名・日付・金額の書き方の違いは bank_csv.py で吸収する
    try:
        rows = parse_bank_csv(csv_text)
    except BankCsvError as e:
        raise RuleViolationError(str(e)) from e

    drafts = []
    seen: dict[str, int] = {}
    for r in rows:
        # 同じ内容の明細が同じファイルに複数ある場合も区別できるよう、出現回数を含めてキーを作る
        base = f"{r.entry_date}|{r.description}|{r.direction}|{r.amount}"
        seen[base] = seen.get(base, 0) + 1
        import_key = hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()

        # ① まずキーワードのルールで推測する（無料・すぐ終わる・結果が毎回同じ）
        account = suggest_account(r.description, r.direction)
        drafts.append(
            BankDraft(
                import_key=import_key,
                entry_date=r.entry_date,
                description=r.description,
                direction=r.direction,
                amount=r.amount,
                account=account,
                suggested_by="rule" if account else None,
            )
        )

    # すでに取り込み済みの明細に印をつける
    keys = [d.import_key for d in drafts]
    existing = set(
        db.scalars(select(JournalEntry.import_key).where(JournalEntry.import_key.in_(keys)))
    )
    for d in drafts:
        d.already_imported = d.import_key in existing

    # ② ルールで推測できず、まだ取り込んでいない明細だけをAIに推測させる
    #    （APIキーがない・エラーのときは何もせず、科目は空欄のまま人が選ぶ）
    targets = [d for d in drafts if d.account is None and not d.already_imported]
    if targets:
        candidates = [name for name in db.scalars(select(Account.name)) if name != BANK_ACCOUNT]
        ai_accounts = suggest_accounts_with_ai(
            [(d.description, d.direction) for d in targets], candidates
        )
        for d in targets:
            account = ai_accounts.get((d.description, d.direction))
            if account:
                d.account = account
                d.suggested_by = "ai"
    return drafts


def commit(db: Session, drafts: list[BankDraft]) -> int:
    """人が確認した下書きを仕訳としてまとめて登録し、登録した件数を返す"""
    if any(d.account is None for d in drafts):
        raise RuleViolationError("勘定科目が選ばれていない明細があります")

    # 相手科目に銀行口座そのものを選ぶと、借方と貸方が同じ科目になってしまう
    if any(d.account == BANK_ACCOUNT for d in drafts):
        raise RuleViolationError(
            f"相手科目に「{BANK_ACCOUNT}」は選べません（借方と貸方が同じ科目になります）"
        )

    ensure_accounts_exist(db, (d.account for d in drafts if d.account))

    keys = [d.import_key for d in drafts]
    if db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.import_key.in_(keys))) > 0:
        raise ConflictError("すでに取り込み済みの明細が含まれています")

    # 出金：費用など（借方）／普通預金（貸方）、入金：普通預金（借方）／売掛金など（貸方）
    for d in drafts:
        if d.direction == "out":
            lines = [
                JournalLine(account=d.account, side="debit", amount=d.amount),
                JournalLine(account=BANK_ACCOUNT, side="credit", amount=d.amount),
            ]
        else:
            lines = [
                JournalLine(account=BANK_ACCOUNT, side="debit", amount=d.amount),
                JournalLine(account=d.account, side="credit", amount=d.amount),
            ]
        db.add(
            JournalEntry(
                entry_date=d.entry_date,
                description=d.description,
                import_key=d.import_key,
                lines=lines,
            )
        )

    try:
        db.commit()  # まとめて1つのトランザクションで保存
    except IntegrityError:
        # APIの確認をすり抜けた重複も、データベースの一意制約で防ぐ
        db.rollback()
        raise ConflictError("すでに取り込み済みの明細が含まれています") from None
    return len(drafts)
