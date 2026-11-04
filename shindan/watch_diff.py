"""前回と今回の診断を比べ、悪くなったところだけを言葉にする。"""

LABELS = {
    "ssl_certificate": "安全な接続の証明書",
    "http_redirect": "安全な入り口への案内",
    "domain_expiry": "ドメインの期限",
    "page_response": "ページの表示",
    "site_software": "ホームページの仕組みの古さ",
    "search_settings": "検索に出るための設定",
    "mobile_view": "スマホ向けの設定",
    "mail_settings": "メールの設定",
    "contact_form": "お問い合わせフォームの送り先",
    "map_listing": "Googleマップとの電話番号",
}
STATE_TEXT = {"ok": "指摘なし", "unknown": "調べられず", "warn": "近いうちに", "critical": "すぐ対応"}
# 調べられなかっただけのものは、悪化として知らせない。
RANK = {"ok": 0, "unknown": 0, "warn": 1, "critical": 2}
NEAR_DAYS = 30


def _by_id(state: dict) -> dict:
    return {check["id"]: check for check in state.get("checks", [])}


def _crossed_near(before: dict | None, now: dict) -> bool:
    days = now.get("facts", {}).get("days_left")
    if days is None or days > NEAR_DAYS:
        return False
    earlier = (before or {}).get("facts", {}).get("days_left")
    return earlier is None or earlier > NEAR_DAYS


def worsened(previous: dict | None, current: dict) -> list[str]:
    """前回が無ければ比べるものが無いので空。項目が前回に無ければ「指摘なし」だったものとして扱う。"""
    if previous is None:
        return []
    before = _by_id(previous)
    lines = []
    for check_id, now in _by_id(current).items():
        old = before.get(check_id)
        old_status = old["status"] if old else "ok"
        label = LABELS.get(check_id, check_id)
        if RANK[now["status"]] > RANK[old_status]:
            lines.append(f"{label}: {STATE_TEXT[old_status]} → {STATE_TEXT[now['status']]}")
        elif _crossed_near(old, now):
            lines.append(f"{label}: 期限まであと{now['facts']['days_left']}日")
    return lines
