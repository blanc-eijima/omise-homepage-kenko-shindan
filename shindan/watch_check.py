"""毎月の自動診断の本体。エージェントのサンドボックスで動かす。キーは要らない。

状態の置き場（メモリストアの中）:
  sites.txt            調べるアドレス（1行1件）
  sites/<host>.json    前回の結果
  reports/latest.md    最新の報告
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shindan.cli import scan
from shindan.guard import UnsafeTarget
from shindan.watch_diff import worsened

JST = timezone(timedelta(hours=9))


def read_sites(state_dir: Path) -> list[str]:
    lines = (state_dir / "sites.txt").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def check_site(url: str, state_dir: Path, scan_site=scan) -> str:
    """1件調べて前回の結果を更新し、報告の1行を返す。"""
    try:
        report = scan_site(url)
    except (UnsafeTarget, OSError, ValueError) as exc:
        return f"- {url}: 調べられませんでした（{type(exc).__name__}）"
    path = state_dir / "sites" / f"{report['host']}.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    lines = worsened(previous, report)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {"checked_at": report["checked_at"], "checks": report["checks"]}
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    if previous is None:
        return f"- {report['host']}: 初回の記録"
    if not lines:
        return f"- {report['host']}: 悪くなった項目なし"
    note = "（デモ用の前回データと比較）" if previous.get("demo_previous") else ""
    return "\n".join([f"- {report['host']}{note}"] + [f"  - {line}" for line in lines])


def run(state_dir: Path, today: str | None = None, scan_site=scan) -> str:
    today = today or datetime.now(JST).date().isoformat()
    rows = [check_site(url, state_dir, scan_site) for url in read_sites(state_dir)]
    text = f"# {today} の毎月の診断\n\n" + "\n".join(rows) + "\n"
    reports = state_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "latest.md").write_text(text, encoding="utf-8")
    (reports / f"{today}.md").write_text(text, encoding="utf-8")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    print(run(parser.parse_args().state))


if __name__ == "__main__":
    main()
