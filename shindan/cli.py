"""URLを受け取り、調査結果をJSONで出す。"""
import json
import sys
from datetime import datetime, timezone

from shindan.checks.domain import check_domain
from shindan.checks.page_checks import (
    check_mobile_view,
    check_page_response,
    check_search_settings,
)
from shindan.checks.site_software import check_site_software
from shindan.checks.ssl_cert import check_certificate, check_http_redirect
from shindan.guard import UnsafeTarget, parse_target
from shindan.page import fetch_top


def scan(raw_url: str) -> dict:
    host = parse_target(raw_url)
    page = fetch_top(host)
    return {
        "host": host,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": [
            check_certificate(host),
            check_http_redirect(host),
            check_domain(host),
            check_page_response(page),
            check_site_software(page),
            check_search_settings(page),
            check_mobile_view(page),
        ],
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    with_explanation = "--explain" in args
    urls = [a for a in args if a != "--explain"]
    if len(urls) != 1:
        print("使い方: python -m shindan.cli [--explain] <URL>", file=sys.stderr)
        return 2
    try:
        report = scan(urls[0])
    except UnsafeTarget as exc:
        print(f"調べられません: {exc}", file=sys.stderr)
        return 2
    if with_explanation:
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
