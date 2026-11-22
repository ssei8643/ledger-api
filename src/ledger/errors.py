"""業務ルールのエラー

サービス層はHTTPを知らずにこれらのエラーを投げ、main.py のハンドラーが
HTTPのステータスコード（404・409・422）に変換して {"detail": メッセージ} を返す。
"""


class LedgerError(Exception):
    """このアプリの業務ルールに関するエラーの基底クラス"""


class NotFoundError(LedgerError):
    """対象が見つからない"""


class ConflictError(LedgerError):
    """すでに取消・取り込み済みなど、今のデータの状態と衝突する"""


class RuleViolationError(LedgerError):
    """簿記や入力のルールに合わない"""
