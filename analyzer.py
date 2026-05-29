"""
Локальный анализ расписания без внешних AI API.
"""
import re
from datetime import date, timedelta
from typing import Optional

ROMANIAN_MONTHS = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4,
    "mai": 5, "iunie": 6, "iulie": 7, "august": 8,
    "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
    "ian": 1, "feb": 2, "mar": 3, "apr": 4, "iun": 6, "iul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

KEYWORDS = {
    "orar": "расписание", "sesiune": "сессия", "exam": "экзамен",
    "examen": "экзамен", "admitere": "поступление", "termen": "дедлайн",
    "deadline": "дедлайн", "licenta": "лицензиатура", "master": "магистратура",
    "curs": "занятия", "semestru": "семестр",
}

class SmartAnalyzer:
    def analyze(self, items: list[tuple[str, str]]) -> dict:
        today = date.today()
        events: list[dict] = []
        important_links: list[dict] = []
        for text, href in items:
            combined = f"{text} {href}".lower()
            categories = [label for key, label in KEYWORDS.items() if key in combined]
            if categories:
                important_links.append({"title": text, "href": href, "categories": categories})
            for parsed in self._extract_dates(combined, today):
                events.append({
                    "date": parsed, "title": text[:60], "href": href,
                    "categories": categories, "days_until": (parsed - today).days,
                })
        events.sort(key=lambda e: e["date"])
        upcoming = [e for e in events if e["days_until"] >= 0][:10]
        recommendations = self._build_recommendations(upcoming, important_links, today)
        return {
            "upcoming": upcoming, "important_links": important_links[:8],
            "recommendations": recommendations, "total_links": len(items),
        }

    def format_report(self, analysis: dict, last_upd: str) -> str:
        import html as html_mod
        esc = html_mod.escape
        bq = lambda body: f"<blockquote expandable>{body}</blockquote>"
        lines = ["<b>🧠 Умный анализ</b> (локально, данные никуда не отправляются)", ""]
        upcoming = analysis.get("upcoming", [])
        if upcoming:
            dates_body = []
            for event in upcoming[:7]:
                d_str = event["date"].strftime("%d.%m.%Y")
                days = event["days_until"]
                when = "сегодня" if days == 0 else ("завтра" if days == 1 else f"через {days} дн.")
                cats = ", ".join(event["categories"]) if event["categories"] else "событие"
                dates_body.append(f"• {d_str} — {esc(event['title'])} ({when}, {esc(cats)})")
            lines += ["<b>📅 Ближайшие даты:</b>", bq("\n".join(dates_body)), ""]
        else:
            lines += [bq("📅 Явных дат в ссылках не найдено."), ""]
        recs = analysis.get("recommendations", [])
        if recs:
            lines += ["<b>✅ Рекомендации:</b>", bq("\n".join(f"• {esc(r)}" for r in recs[:6])), ""]
        important = analysis.get("important_links", [])
        if important:
            preview = "\n".join(f"• {esc(item['title'][:50])}" for item in important[:5])
            lines += ["<b>🔗 Важные ссылки:</b>", bq(preview)]
        lines += [f"\n🕒 Данные обновлены: {esc(last_upd)}", f"📊 Всего ссылок: {analysis.get('total_links', 0)}"]
        return "\n".join(lines)

    def _extract_dates(self, text: str, today: date) -> list[date]:
        found, seen = [], set()
        patterns = [
            (r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", self._parse_dmy),
            (r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", self._parse_ymd),
            (r"\b(\d{1,2})\.(\d{1,2})\.(\d{2})\b", self._parse_dmy_short),
            (r"\b(\d{1,2})\s+(ianuarie|februarie|martie|aprilie|mai|iunie|iulie|"
             r"august|septembrie|octombrie|noiembrie|decembrie)(?:\s+(\d{4}))?\b", self._parse_romanian),
            (r"\b(\d{1,2})\.(\d{1,2})\b", self._parse_dm),
        ]
        for pattern, parser in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                parsed = parser(match, today)
                if parsed and parsed not in seen:
                    seen.add(parsed)
                    found.append(parsed)
        return found

    def _parse_dmy(self, m, _): 
        try: return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError: return None
    def _parse_dmy_short(self, m, _):
        try: return date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError: return None
    def _parse_ymd(self, m, _):
        try: return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: return None
    def _parse_romanian(self, m, today):
        month = ROMANIAN_MONTHS.get(m.group(2).lower())
        if not month: return None
        day = int(m.group(1))
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            parsed = date(year, month, day)
            if not m.group(3) and parsed < today: parsed = date(year + 1, month, day)
            return parsed
        except ValueError: return None
    def _parse_dm(self, m, today):
        try:
            day, month = int(m.group(1)), int(m.group(2))
            parsed = date(today.year, month, day)
            if parsed < today - timedelta(days=30): parsed = date(today.year + 1, month, day)
            return parsed
        except ValueError: return None

    def _build_recommendations(self, upcoming, important_links, today):
        recs = []
        for event in upcoming:
            days, d_str = event["days_until"], event["date"].strftime("%d.%m")
            if days <= 3:
                recs.append(f"Проверь расписание {d_str} — скоро: {event['title'][:40]}")
            elif days <= 7 and "сессия" in event.get("categories", []):
                recs.append(f"Сессия {d_str}: следи за обновлениями orar на сайте")
        if any("расписание" in i.get("categories", []) for i in important_links):
            recs.append("Есть свежие ссылки на orar — проверь PDF/Google Sheets")
        if not recs:
            recs += ["Регулярно проверяй /raspisanie", "Используй /orar для полного списка"]
        recs.append(f"Следующая проверка рекомендуется: {(today + timedelta(days=1)).strftime('%d.%m')}")
        return recs
