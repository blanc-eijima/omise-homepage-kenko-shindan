"""レビュー役の評価。問題を仕込んだ依頼文を見つけ、正しい依頼文を止めないかをモデルごとに測る。
費用がかかる（1回の実行で20回ほどClaudeを呼ぶ）。実行: python -m evals.review_letters
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from shindan.config import read_secret
from shindan.review import review_requests

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
    with ThreadPoolExecutor(4) as pool:
        for (model, name), issues in pool.map(run, jobs):
            right = bool(issues) == table[name][1]
            print(f"{'正解' if right else '誤り'} {model} {name}: {issues[:1]}")


if __name__ == "__main__":
    main()
