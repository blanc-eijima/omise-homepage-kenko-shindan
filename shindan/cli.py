"""URLを受け取り、調査結果をJSONで出す。"""
import argparse
import json
import sys
from datetime import datetime, timezone

from shindan.checks.contact_form import check_contact_form
from shindan.checks.domain import check_domain
from shindan.checks.mail_settings import check_mail_settings
from shindan.checks.map_listing import check_map_listing
from shindan.checks.page_checks import (
    check_mobile_view,
    check_page_response,
    check_search_settings,
)
from shindan.checks.site_software import check_site_software
from shindan.checks.ssl_cert import check_certificate, check_http_redirect
from shindan.checks.vendor_hints import collect_hints
from shindan.config import read_secret
from shindan.guard import UnsafeTarget, parse_target
from shindan.page import fetch_top

# 既存の共用キー（GOOGLE_PLACES_API_KEY）と取り違えないよう、専用の名前にする。
PLACES_KEY_NAME = "SHINDAN_PLACES_API_KEY"


def scan(raw_url: str, shop_name: str | None = None) -> dict:
    host = parse_target(raw_url)
    page = fetch_top(host)
    checks = [
        check_certificate(host),
        check_http_redirect(host),
        check_domain(host),
        check_page_response(page),
        check_site_software(page),
        check_search_settings(page),
        check_mobile_view(page),
        check_mail_settings(host),
        check_contact_form(page),
    ]
    # キーが無ければ項目ごと外す＝調べていないことを読み解きにも書かせない。
    if key := read_secret(PLACES_KEY_NAME):
        checks.append(check_map_listing(page, host, key, shop_name))
    return {
        "host": host,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": checks,
        "hints": collect_hints(host, page),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="お店のホームページ健康診断")
    parser.add_argument("url")
    parser.add_argument("--explain", action="store_true", help="Claudeの読み解きと依頼文を付ける")
    parser.add_argument("--name", help="Googleマップで探すお店の名前と地域")
    return parser.parse_args()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = _parse_args()
    try:
        report = scan(args.url, args.name)
    except UnsafeTarget as exc:
        print(f"調べられません: {exc}", file=sys.stderr)
        return 2
    if args.explain:
        # 調査結果を失わないよう、読み解きの失敗は調査結果を出してから知らせる。
        from shindan.explain import ExplainError, explain

        try:
            report["explanation"] = explain(report)
        except ExplainError as exc:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            print(f"読み解きを作れませんでした: {exc}", file=sys.stderr)
            return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
