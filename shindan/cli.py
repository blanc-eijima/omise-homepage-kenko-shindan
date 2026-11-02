"""URLを受け取り、調査結果をJSONで出す。"""
import json
import sys
from datetime import datetime, timezone

from shindan.checks.domain import check_domain
from shindan.checks.ssl_cert import check_certificate, check_http_redirect
from shindan.guard import UnsafeTarget, parse_target


def scan(raw_url: str) -> dict:
    host = parse_target(raw_url)
    return {
        "host": host,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": [
            check_certificate(host),
            check_http_redirect(host),
            check_domain(host),
        ],
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print("使い方: python -m shindan.cli <URL>", file=sys.stderr)
        return 2
    try:
        report = scan(sys.argv[1])
    except UnsafeTarget as exc:
        print(f"調べられません: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
