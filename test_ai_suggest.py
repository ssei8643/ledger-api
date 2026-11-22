import ai_suggest
from ai_suggest import suggest_accounts_with_ai

ACCOUNTS = ["消耗品費", "会議費", "事業主貸", "売掛金"]


def fake_ask_claude(answers):
    """本物のAIの代わりに、決まった答えを返す関数を作る。受け取った内容も記録する"""
    calls = []

    def fake(items, accounts):
        calls.append(items)
        return answers

    return fake, calls


def test_APIキーがなければAIは呼ばれず空のまま(monkeypatch):
    fake, calls = fake_ask_claude([{"index": 0, "account": "消耗品費"}])
    monkeypatch.setattr(ai_suggest, "_ask_claude", fake)

    assert suggest_accounts_with_ai([("ﾎｰﾑｾﾝﾀｰ", "out")], ACCOUNTS) == {}
    assert calls == []


def test_AIの答えは科目マスタにある科目だけ使う(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake, _ = fake_ask_claude(
        [
            {"index": 0, "account": "消耗品費"},
            {"index": 1, "account": "存在しない科目"},
            {"index": 2, "account": "不明"},
            {"index": 99, "account": "会議費"},  # 範囲外の番号
        ]
    )
    monkeypatch.setattr(ai_suggest, "_ask_claude", fake)

    items = [("ﾎｰﾑｾﾝﾀｰ", "out"), ("ナゾノシハライ", "out"), ("ｶｰﾄﾞ", "out")]
    assert suggest_accounts_with_ai(items, ACCOUNTS) == {("ﾎｰﾑｾﾝﾀｰ", "out"): "消耗品費"}


def test_AIがエラーになっても例外にならず空のまま(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def broken(items, accounts):
        raise TimeoutError("応答がありません")

    monkeypatch.setattr(ai_suggest, "_ask_claude", broken)
    assert suggest_accounts_with_ai([("ﾎｰﾑｾﾝﾀｰ", "out")], ACCOUNTS) == {}


def test_同じ摘要の明細はまとめて1回だけAIに聞く(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake, calls = fake_ask_claude([{"index": 0, "account": "会議費"}])
    monkeypatch.setattr(ai_suggest, "_ask_claude", fake)

    items = [("カフェ", "out"), ("カフェ", "out"), ("カフェ", "out")]
    assert suggest_accounts_with_ai(items, ACCOUNTS) == {("カフェ", "out"): "会議費"}
    assert calls == [[("カフェ", "out")]]
