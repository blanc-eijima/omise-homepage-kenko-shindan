"""メールの設定（MX・SPF・DMARC）を公開のDNSで調べる。"""
import json
import urllib.parse
import urllib.request

from shindan.checks.domain import registrable_domain

TIMEOUT = 10
DOH_URL = "https://dns.google/resolve?"
NOERROR = 0
NXDOMAIN = 3


def _query(name: str, record_type: str) -> list[str]:
    """該当レコードの値を返す。無ければ空。DNSの一時的な失敗は OSError にする。"""
    query = urllib.parse.urlencode({"name": name, "type": record_type})
    request = urllib.request.Request(DOH_URL + query, headers={"User-Agent": "omise-kenko-shindan/0.1"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.load(response)
    if payload.get("Status") not in (NOERROR, NXDOMAIN):
        raise OSError(f"DNSの応答が異常です: {payload.get('Status')}")
    wanted = {"A": 1, "NS": 2, "PTR": 12, "MX": 15, "TXT": 16}[record_type]
    return [a["data"] for a in payload.get("Answer", []) if a.get("type") == wanted]


def _txt_value(raw: str) -> str:
    """TXTは "v=spf1 " "include:a" のように分割されることがある。"""
    return raw.replace('" "', "").strip('"').strip()


def judge_mail(mx: list[str], txt: list[str], dmarc_txt: list[str]) -> dict:
    spf = [t for t in map(_txt_value, txt) if t.lower().startswith("v=spf1")]
    dmarc = [t for t in map(_txt_value, dmarc_txt) if t.lower().startswith("v=dmarc1")]
    facts = {"mail_in_use": bool(mx), "spf_records": len(spf), "dmarc_present": bool(dmarc)}
    # メールを使っていないドメインに、メールの設定不足は指摘しない。
    healthy = not mx or (len(spf) == 1 and bool(dmarc))
    return {"id": "mail_settings", "status": "ok" if healthy else "warn", "facts": facts}


def check_mail_settings(host: str) -> dict:
    domain = registrable_domain(host)
    try:
        return judge_mail(
            _query(domain, "MX"), _query(domain, "TXT"), _query(f"_dmarc.{domain}", "TXT")
        )
    except (OSError, ValueError) as exc:
        return {"id": "mail_settings", "status": "unknown", "facts": {"error": str(exc)}}
