"""レビュー役の評価。問題を仕込んだ依頼文を見つけ、正しい依頼文を止めないかをモデルごとに測る。
費用がかかる（1回の実行で20回ほどClaudeを呼ぶ）。実行: python -m evals.review_letters

合格ライン（本番で使うモデル REVIEW_MODEL にだけ課す。他のモデルは比較用に表示するだけ）:
- 仕込んだ問題の見逃し 0件（間違った依頼文が店主へ渡るのを防ぐのが役目のため）
- 正しい依頼文を止めた件数 0件（止めると書き直しが走り、費用と待ち時間が増えるため）
満たさなければ終了コード1で終わる。
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from shindan.config import read_secret
from shindan.review import REVIEW_MODEL, review_requests

MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5"]
RUNS = 2
CASE_FILE = Path(__file__).parent / "expired_badssl.json"


def _replace(old: str, new: str):
    def apply(letters: list[dict]) -> list[dict]:
        assert any(old in letter["body"] for letter in letters), old
        return [{**letter, "body": letter["body"].replace(old, new)} for letter in letters]

    return apply


def _readdress(to: str):
    return lambda letters: [{**letter, "to": to} for letter in letters]


def cases(expires: str, domain: str) -> dict:
    """名前 → (文面の加工, 問題を見つけるべきか)"""
    return {
        "正しい依頼文": (lambda letters: letters, False),
        "日付の取り違え": (_replace(expires, "2027-04-08"), True),
        "対象のドメイン違い": (_replace(domain, "other-shop.example"), True),
        "宛先の間違い": (_readdress("ドメイン会社"), True),
    }


def score(results: list[tuple[str, bool, bool]]) -> dict:
    """(モデル, 問題を見つけるべきか, 見つけたか) の列 → モデルごとの見逃しと誤って止めた件数。"""
    tally: dict = {}
    for model, should_find, found in results:
        t = tally.setdefault(model, {"missed": 0, "false_stop": 0, "total": 0})
        t["total"] += 1
        if should_find and not found:
            t["missed"] += 1
        if found and not should_find:
            t["false_stop"] += 1
    return tally


def passed(tally: dict, model: str = REVIEW_MODEL) -> bool:
    t = tally.get(model)
    return bool(t) and t["missed"] == 0 and t["false_stop"] == 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    data = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    client = anthropic.Anthropic(api_key=read_secret("ANTHROPIC_API_KEY"))
    table = cases(data["expires"], data["domain"])

    def run(job):
        model, name = job
        change, _ = table[name]
        return job, review_requests(client, data["scan"], change(data["requests"]), model)

    jobs = [(m, n) for m in MODELS for n in table for _ in range(RUNS)]
    results = []
    with ThreadPoolExecutor(4) as pool:
        for (model, name), issues in pool.map(run, jobs):
            should_find = table[name][1]
            right = bool(issues) == should_find
            results.append((model, should_find, bool(issues)))
            print(f"{'正解' if right else '誤り'} {model} {name}: {issues[:1]}")

    tally = score(results)
    print()
    for model, t in tally.items():
        mark = "（本番）" if model == REVIEW_MODEL else "（比較）"
        print(f"{model}{mark}: {t['total']}回 見逃し {t['missed']} / 正しい依頼文を止めた {t['false_stop']}")
    ok = passed(tally)
    print(f"判定: {'合格' if ok else '不合格'}（{REVIEW_MODEL} で見逃し0・止めすぎ0）")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
