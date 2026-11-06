"""公開時の回数制限。費用が青天井にならないよう、調査の入口で数える。"""
import threading
import time
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
DAILY_LIMIT = 30
# 審査期間（提出締切の11/8〜ライブ審査の11/10、日本時間）だけ上げる。過ぎたら自動で30へ戻る。
REVIEW_DAYS = ("2026-11-08", "2026-11-10")
REVIEW_DAILY_LIMIT = 100
PER_IP_LIMIT = 5
PER_IP_WINDOW = 3600

DAILY_MESSAGE = "本日の診断の受付は終了しました。明日もう一度お試しください"
PER_IP_MESSAGE = "短い時間に続けて診断されています。1時間ほどあけてお試しください"


def daily_limit(day: str) -> int:
    """日本時間の日付（YYYY-MM-DD）→ その日の全体の上限。"""
    first, last = REVIEW_DAYS
    return REVIEW_DAILY_LIMIT if first <= day <= last else DAILY_LIMIT


class UsageLimits:
    """全体の1日の上限と、1つの接続元の1時間の上限。"""

    # ponytail: 記録はメモリだけ。デプロイや障害で再起動すると数え直しになる。
    # 本当の歯止めは Console の月額上限。再起動が問題になったらボリュームへ。

    def __init__(self, clock=time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self._day = ""
        self._count = 0
        self._by_ip: dict[str, list[float]] = {}

    def take(self, ip: str) -> str | None:
        """1回分を確保する。断るときは店主に見せる文を返す。"""
        now = self._clock()
        with self._lock:
            day = datetime.fromtimestamp(now, JST).date().isoformat()
            if day != self._day:
                self._day, self._count, self._by_ip = day, 0, {}
            recent = [t for t in self._by_ip.get(ip, []) if now - t < PER_IP_WINDOW]
            if len(recent) >= PER_IP_LIMIT:
                return PER_IP_MESSAGE
            if self._count >= daily_limit(day):
                return DAILY_MESSAGE
            self._by_ip[ip] = recent + [now]
            self._count += 1
            return None

    def give_back(self, ip: str) -> None:
        """調べずに断った入力（打ち間違いなど）は数えない。"""
        with self._lock:
            if self._by_ip.get(ip):
                self._by_ip[ip] = self._by_ip[ip][:-1]
                self._count -= 1

    def used_today(self) -> int:
        with self._lock:
            return self._count

    def limit_today(self) -> int:
        return daily_limit(datetime.fromtimestamp(self._clock(), JST).date().isoformat())
