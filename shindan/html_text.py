"""診断するページのHTMLから、タグを外した文字とリンクを取り出す。

ページはお店のサイト（誰でも用意できる）から最大2MB届く。正規表現の
`<(script|style)\b.*?</\1>|<[^>]+>` や `<a ...>(.*?)</a>` は、閉じていない
タグを並べたページで文字数の2乗の時間がかかり、公開版の処理が止まる。
ここでは文字列の検索だけで1回なめるように読み、時間を文字数に比例させる。
"""
import re
import string
from collections.abc import Iterator

_RAW_TEXT = ("script", "style")
# タグ名の大小だけをそろえる。str.lower() は「İ」で2文字に増えて、位置がずれる。
_ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)
_HREF = re.compile(r"""href=["']([^"'#]+)["']""", re.IGNORECASE)


def _is_word_char(text: str, index: int) -> bool:
    return index < len(text) and (text[index].isalnum() or text[index] == "_")


def _raw_text_name(lower: str, start: int) -> str | None:
    """start の「<」が <script / <style の始まりなら、その名前を返す。"""
    for name in _RAW_TEXT:
        end = start + 1 + len(name)
        if lower.startswith(name, start + 1) and not _is_word_char(lower, end):
            return name
    return None


def strip_tags(html: str) -> str:
    """script・style は中身ごと、ほかのタグはタグだけを空白に置き換える。

    閉じタグの無い script・style は、開始タグだけを外す（これまでの正規表現と同じ）。
    「>」が後ろに無い「<」は、そのまま文字として残す。
    """
    lower = html.translate(_ASCII_LOWER)
    out: list[str] = []
    position = 0
    unclosed: set[str] = set()  # 後ろに閉じタグが無いと分かった名前。探し直さない
    no_more_gt = False
    while True:
        start = html.find("<", position)
        if start < 0 or no_more_gt:
            out.append(html[position:])
            return "".join(out)
        out.append(html[position:start])
        name = _raw_text_name(lower, start)
        if name and name not in unclosed:
            close = lower.find(f"</{name}>", start)
            if close >= 0:
                out.append(" ")
                position = close + len(name) + 3
                continue
            unclosed.add(name)
        if html.startswith(">", start + 1):  # 「<>」はタグとして扱わない
            out.append("<")
            position = start + 1
            continue
        end = html.find(">", start + 2)
        if end < 0:
            no_more_gt = True
            position = start
            continue
        out.append(" ")
        position = end + 1


def _last_href(html: str, start: int, end: int) -> re.Match | None:
    """タグの中に href が2つあれば後ろのほう（これまでの正規表現の `[^>]*` は最長一致）。"""
    found = None
    while (match := _HREF.search(html, start, end)) is not None:
        found, start = match, match.start() + 1
    return found


def iter_links(html: str) -> Iterator[tuple[str, str]]:
    """<a href="…">文字</a> の (href, 文字) を出てきた順に返す。

    href に「#」が入るもの・引用符の無いものは読まない（これまでの正規表現と同じ）。
    """
    lower = html.translate(_ASCII_LOWER)
    position = 0
    while True:
        start = lower.find("<a", position)
        if start < 0:
            return
        position = start + 2
        if _is_word_char(lower, start + 2):
            continue  # <abbr> などは別のタグ
        tag_end = html.find(">", start)
        if tag_end < 0:
            return
        href = _last_href(html, start, tag_end)
        if href is None:
            # 「>」までにある別の「<a」も同じ「>」で閉じ、href が無いのは同じ。読み直さずに先へ進む
            position = tag_end + 1
            continue
        close = lower.find("</a>", tag_end)
        if close < 0:
            return  # 後ろに </a> が無ければ、この先のリンクも閉じない
        yield href.group(1), html[tag_end + 1:close]
        position = close + 4
