"""Claudeの読み解きが、調査結果に無いことを書いていないか検査する。"""
import json
import re
import unicodedata

NOT_A_REQUEST = {"自分で", "依頼は不要"}
OWNER_FIELDS = ("what_is_happening", "trouble_if_left", "what_to_do")
JARGON = ("SSL", "TLS", "DNS", "RDAP", "WHOIS", "HTTP", "HTTPS", "リダイレクト")
# 調べていない項目について書くと、架空の指摘になる。キーは調査項目のid。
TOPICS = {
    "site_software": ("WordPress", "PHP"),
    "mail_settings": ("SPF", "DMARC", "迷惑メール"),
    "contact_form": ("フォーム",),
    "search_settings": ("noindex", "robots", "検索に出"),
    "mobile_view": ("スマホ", "viewport"),
    "map_listing": ("Googleマップ", "Google マップ"),
}

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NUMBER = re.compile(r"\d+")
# 「2つ」「3件」は文章の数え方で、調査の事実ではない。「3日」「3000円」は止める。
_COUNT = re.compile(r"\d+(?=つ|点|件|項目|通|か所|箇所)")
_DOMAIN = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+")
# robots.txt や wp-config.php はファイルの名前で、ドメイン名ではない。
_FILE_NAME = (".txt", ".php", ".html", ".htm", ".xml", ".css", ".js")


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def _numbers(text: str) -> set[int]:
    return {int(token) for token in _NUMBER.findall(_normalize(text))}


def _domains(text: str) -> set[str]:
    return {
        d for d in _DOMAIN.findall(_normalize(text))
        if not d[0].isdigit() and not d.endswith(_FILE_NAME)
    }


def _all_text(explanation: dict) -> str:
    return json.dumps(explanation, ensure_ascii=False)


def _check_facts(explanation: dict, scan: dict) -> list[str]:
    """数字とドメイン名は、調査結果に現れるものだけを許す。"""
    # ponytail: 数字が調査結果のどこかにあれば通す（文脈までは見ない）。
    # 別の項目の数字を取り違える誤りは止められない。起きたら項目ごとの突合へ。
    known = json.dumps(
        {"host": scan["host"], "facts": [c["facts"] for c in scan["checks"]]},
        ensure_ascii=False,
    )
    text = _COUNT.sub(" ", _normalize(_all_text(explanation)))
    problems = [f"調査結果に無い数字: {n}" for n in sorted(_numbers(text) - _numbers(known))]
    problems += [f"調査結果に無いドメイン名: {d}" for d in sorted(_domains(text) - _domains(known))]
    return problems


def _check_topics(explanation: dict, scan: dict) -> list[str]:
    scanned = {c["id"] for c in scan["checks"]}
    text = _all_text(explanation).lower()
    return [
        f"調べていない項目への言及: {word}"
        for check_id, words in TOPICS.items()
        if check_id not in scanned
        for word in words
        if word.lower() in text
    ]


def _check_cards(explanation: dict, scan: dict) -> list[str]:
    """問題のある項目すべてに1枚ずつカードがあること。"""
    expected = {c["id"] for c in scan["checks"] if c["status"] != "ok"}
    found = [card["check_id"] for card in explanation["cards"]]
    problems = [f"カードの無い項目: {i}" for i in sorted(expected - set(found))]
    problems += [f"問題の無い項目のカード: {i}" for i in sorted(set(found) - expected)]
    problems += [f"カードの重複: {i}" for i in sorted({i for i in found if found.count(i) > 1})]
    return problems


def _check_requests(explanation: dict) -> list[str]:
    """カードの依頼先と依頼文の宛先が、過不足なく一致すること。"""
    needed = {card["who_to_ask"] for card in explanation["cards"]} - NOT_A_REQUEST
    written = [request["to"] for request in explanation["requests"]]
    problems = [f"依頼文の無い依頼先: {t}" for t in sorted(needed - set(written))]
    problems += [f"カードに無い依頼先: {t}" for t in sorted(set(written) - needed)]
    problems += [f"依頼文の重複: {t}" for t in sorted({t for t in written if written.count(t) > 1})]
    return problems


def _check_jargon(explanation: dict) -> list[str]:
    """店主が読む欄に専門用語を残さない。依頼文は業者宛なので対象外。"""
    fields = [explanation["summary"]]
    fields += [card[name] for card in explanation["cards"] for name in OWNER_FIELDS]
    text = "\n".join(fields)
    # ドメイン名の中の文字（badssl.com の ssl など）は専門用語として数えない。
    words = _DOMAIN.sub(" ", unicodedata.normalize("NFKC", text).lower())
    problems = [
        f"店主向けの欄の専門用語: {word}"
        for word in JARGON
        if re.search(rf"(?<![a-z]){re.escape(word.lower())}(?![a-z])", words)
    ]
    problems += [f"店主向けの欄の日付の形: {d}" for d in _ISO_DATE.findall(text)]
    return problems


def find_problems(explanation: dict, scan: dict) -> list[str]:
    return (
        _check_facts(explanation, scan)
        + _check_topics(explanation, scan)
        + _check_cards(explanation, scan)
        + _check_requests(explanation)
        + _check_jargon(explanation)
    )
