import pytest

from ledger.config import normalize_database_url


@pytest.mark.parametrize(
    "url, expected",
    [
        # ホスティングサービスが渡す形は、psycopg 3 を使う書き方にそろえる
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        # すでにドライバを指定しているURLやSQLiteはそのまま
        ("postgresql+psycopg://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("sqlite:///./ledger.db", "sqlite:///./ledger.db"),
    ],
)
def test_データベースのURLをドライバに合わせてそろえる(url, expected):
    assert normalize_database_url(url) == expected
