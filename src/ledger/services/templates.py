"""よく使う仕訳のテンプレート"""

from ledger.schemas import JournalTemplate, TemplateLine


def make_template(name: str, description: str, debit: str, credit: str) -> JournalTemplate:
    return JournalTemplate(
        name=name,
        description=description,
        lines=[
            TemplateLine(account=debit, side="debit"),
            TemplateLine(account=credit, side="credit"),
        ],
    )


TEMPLATES = [
    make_template("交通費（現金払い）", "交通費", "旅費交通費", "現金"),
    make_template("消耗品の購入（現金払い）", "消耗品購入", "消耗品費", "現金"),
    make_template("通信費（口座引き落とし）", "通信費", "通信費", "普通預金"),
    make_template("売上（掛け）", "売上", "売掛金", "売上高"),
    make_template("売掛金の入金（振込）", "売掛金入金", "普通預金", "売掛金"),
    make_template("生活費の引き出し", "生活費の引き出し", "事業主貸", "普通預金"),
]
