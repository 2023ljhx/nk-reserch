#!/usr/bin/env python3
"""안보 일일 브리핑 사이트 생성기: RSS 수집 -> Claude 분석 -> docs/ 정적 HTML"""
import calendar
import html
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import feedparser
import markdown

MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
OUT = Path("docs")
PER_FEED = 12    # 피드당 최대 기사 수
MAX_AGE_H = 48   # 이 시간보다 오래된 기사는 제외

# 주소가 바뀌거나 막히면 그 피드만 건너뜀. 자유롭게 추가·삭제하면 됨.
FEEDS = {
    "TASS(러)": "https://tass.ru/rss/v2.xml",
    "TASS(영)": "https://tass.com/rss/v2.xml",
    "Interfax(러)": "https://www.interfax.ru/rss.asp",
    "RIA(러)": "https://ria.ru/export/rss2/archive/index.xml",
    "크렘린": "http://kremlin.ru/events/all/feed",
    "연합 북한": "https://www.yna.co.kr/rss/northkorea.xml",
    "연합 정치": "https://www.yna.co.kr/rss/politics.xml",
    "NK News": "https://www.nknews.org/feed/",
    "The Diplomat": "https://thediplomat.com/feed/",
    "BBC Asia": "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Japan Times": "https://www.japantimes.co.jp/feed/",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
}

SYSTEM = """당신은 국책 싱크탱크 소속 15년 차 유라시아·북러 지정학 OSINT 수석 연구원임.
입력은 최근 48시간의 뉴스 헤드라인과 요약임. 입력에 없는 사실은 단정하지 않고, 추론은 "추정"으로 표시함.
북한, 러시아, 중국, 미국, 한국, 일본의 안보·정치 이슈를 중심으로 오늘의 브리핑을 작성함.
러시아어 기사는 직역하지 않고 외교적 수사와 은어에 숨은 의도를 해독함.
문체는 건조한 보고서 톤(~함, ~임)으로 쓰고, 굵은 글씨 기호(별표 두 개)는 쓰지 않으며 강조는 “ ” 큰따옴표로 함.
기사 문장은 15단어 넘게 옮기지 않고 자기 말로 요약함.
투자 관련 내용은 시나리오와 리스크 요인으로만 쓰고 매수·매도 권고는 하지 않음.

마크다운으로 아래 구성만 출력함.
## 1. Executive Summary
- 핵심 3개 불릿. 마지막 불릿은 긴급도 “주목(Watch)”, “경고(Alert)”, “즉시조치(Critical)” 중 하나와 근거
## 2. 국가별 동향
### 북한, 러시아, 중국, 미국, 한국, 일본 각각 ### 제목 아래 2~3개 불릿 (새 소식이 없으면 “특이동향 없음”)
## 3. Diplomatic Nuance
- 주목할 키워드: 러시아어 원어 - 이 맥락에서의 실제 정치적 의도 (1~3개)
- 숨은 의도 분석: 표면 메시지, 진짜 타겟, 정책 신호
## 4. Geopolitical Impact
- 한반도 및 역내 안보, 글로벌 방산·에너지·공급망을 각각 0~1개월과 1~3개월로 구분
## 5. Strategic Insight
- 최종 평가 2~3문장과 모니터링 표(항목 | 추적 대상 | 긴급도 | 확인 방법) 4~6행
## 6. 신뢰도
- 🟢High / 🟡Medium / 🟠Low / 🔴Speculative 중 하나와 한 줄 사유"""

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#F2F4F6;--fg:#1B2733;--mute:#5D6B79;--rule:#D5DBE1;--acc:#1F5F8B}
@media(prefers-color-scheme:dark){:root{--bg:#10161C;--fg:#E3E8ED;--mute:#93A1AE;--rule:#26323D;--acc:#7DB4D9}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.75 "Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",system-ui,sans-serif}
main{max-width:720px;margin:0 auto;padding:max(24px,env(safe-area-inset-top)) 20px 64px}
header{border-bottom:2px solid var(--fg);padding-bottom:16px}
header h1{margin:0;font-size:clamp(28px,7vw,40px);line-height:1.2;letter-spacing:-.02em}
header p{margin:6px 0 0;color:var(--mute)}
h2{margin:40px 0 8px;padding-top:16px;border-top:1px solid var(--rule);font-size:20px}
h3{margin:20px 0 4px;font-size:16px;color:var(--acc)}
ul{padding-left:1.1em}li{margin:6px 0}
.tbl{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid var(--rule);padding:8px 10px;text-align:left;vertical-align:top}
a{color:var(--acc)}
nav a{display:inline-block;margin:0 12px 4px 0}
details{margin-top:32px;color:var(--mute);font-size:14px}
footer{margin-top:40px;color:var(--mute);font-size:13px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
</style></head><body><main>
<header><h1>__DATE__</h1><p>북한, 러시아, 중국, 미국, 한국, 일본 안보 브리핑</p></header>
__BODY__
<details><summary>수집한 기사 __COUNT__건</summary><ul>__SRC__</ul></details>
<footer><p>지난 브리핑</p><nav>__NAV__</nav>
<p>공개 기사 헤드라인을 바탕으로 AI가 작성한 분석임. 정책·투자 판단 전에 원문 확인이 필요함.</p></footer>
</main></body></html>"""


def clean(text, limit):
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def collect():
    items, cutoff = [], datetime.now(timezone.utc).timestamp() - MAX_AGE_H * 3600
    for name, url in FEEDS.items():
        n = 0
        try:
            feed = feedparser.parse(url, agent="Mozilla/5.0 (briefing-bot)")
            for e in feed.entries:
                ts = e.get("published_parsed") or e.get("updated_parsed")
                if ts and calendar.timegm(ts) < cutoff:
                    continue
                title = clean(e.get("title"), 200)
                if title:
                    items.append({"src": name, "title": title,
                                  "sum": clean(e.get("summary"), 200),
                                  "link": e.get("link", "")})
                    n += 1
                if n >= PER_FEED:
                    break
            print(f"[ok] {name}: {n}")
        except Exception as err:
            print(f"[skip] {name}: {err}")
    return items


def analyze(items, today):
    digest = "\n".join(f"[{i['src']}] {i['title']} | {i['sum']}" for i in items)
    msg = anthropic.Anthropic().messages.create(
        model=MODEL,
        max_tokens=5000,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"오늘은 {today} (KST)임. 기사 목록:\n{digest}"}],
    )
    return msg.content[0].text


def main():
    now = datetime.now(timezone(timedelta(hours=9)))
    today = now.strftime("%Y-%m-%d")
    items = collect()
    if len(items) < 5:
        raise SystemExit("수집된 기사가 너무 적어 중단함")

    body = markdown.markdown(analyze(items, today), extensions=["tables"])
    body = body.replace("<table>", '<div class="tbl"><table>').replace("</table>", "</table></div>")

    OUT.mkdir(exist_ok=True)
    dates = sorted({p.stem for p in OUT.glob("20*.html")} | {today}, reverse=True)[:60]
    nav = "".join(f'<a href="{d}.html">{d}</a>' for d in dates)
    src = "".join(
        f'<li><a href="{html.escape(i["link"])}">{html.escape(i["src"])} {html.escape(i["title"])}</a></li>'
        for i in items
    )
    day = f'{now.year}년 {now.month}월 {now.day}일 {"월화수목금토일"[now.weekday()]}요일'
    page = (PAGE.replace("__TITLE__", f"안보 브리핑 {today}")
                .replace("__DATE__", day)
                .replace("__BODY__", body)
                .replace("__COUNT__", str(len(items)))
                .replace("__SRC__", src)
                .replace("__NAV__", nav))
    (OUT / f"{today}.html").write_text(page, encoding="utf-8")
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print("완료:", today)


if __name__ == "__main__":
    main()
