import pytest


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    # 手元にAPIキーが設定されていても、テストでは本物のAIを呼ばない
    # （費用がかかる・結果が毎回同じとは限らない・ネットがないと失敗する）
    # AIを使うテストでは、偽のキーと偽の応答を自分で用意する
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
