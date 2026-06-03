"""
Студентский помощник - анализирует расписание по учебным темам
и даёт умные подсказки для подготовки к экзаменам и сессиям.
"""
import re
from datetime import date, timedelta

# Словарь дисциплин и их синонимов
SUBJECT_KEYWORDS = {
    "math": ["математика", "мат-ка", "calculus", "algebra", "geometry", "анализ"],
    "programming": ["програм", "python", "java", "c++", "coding", "code", "algorithm", "алгоритм"],
    "physics": ["физик", "механик", "термо", "электро"],
    "chemistry": ["химия", "реакц", "молекул"],
    "english": ["english", "английск", "language", "языка"],
    "Romanian": ["romanian", "румынск", "limbă"],
    "databases": ["база", "database", "sql", "nosql", "mongodb"],
    "web": ["web", "html", "css", "javascript", "react", "node"],
    "ai": ["ai", "machine", "learning", "neural", "deep", "нейро", "мл"],
    "systems": ["систем", "operating", "linux", "windows", "kernel"],
}

# Советы по подготовке в зависимости от количества дней
PREP_TIPS = {
    "urgent": [
        "⚡ Повтори ключевые концепции",
        "⚡ Сделай краткий конспект",
        "⚡ Реши примеры из прошлых работ",
        "⚡ Спи достаточно перед экзаменом",
    ],
    "week": [
        "📚 Начни с основ, переходи к сложному",
        "📚 Найди пробелы в знаниях",
        "📚 Сделай шпаргалки по формулам",
        "📚 Занимайся 2-3 часа в день",
    ],
    "month": [
        "🎯 Планомерно проходи материал",
        "🎯 Реши все задачи из конспекта",
        "🎯 Участвуй в практических занятиях",
        "🎯 Записывай вопросы для преподавателя",
    ],
}

class StudyCoach:
    """Анализирует расписание по учебным темам и даёт подсказки."""
    
    def analyze_schedule(self, items: list[tuple[str, str]], upcoming_events: list[dict]) -> dict:
        """
        Анализирует расписание и предлагает учебный план.
        
        Args:
            items: список (название, ссылка) из кэша
            upcoming_events: список предстоящих событий с датами
        
        Returns:
            dict с анализом по предметам и рекомендациями
        """
        today = date.today()
        subjects_found = self._detect_subjects(items)
        exam_schedule = self._group_by_subject(upcoming_events, subjects_found)
        study_plan = self._build_study_plan(exam_schedule, today)
        
        return {
            "subjects": subjects_found,
            "exam_schedule": exam_schedule,
            "study_plan": study_plan,
        }
    
    def _detect_subjects(self, items: list[tuple[str, str]]) -> dict[str, int]:
        """Определяет какие предметы упоминаются в расписании."""
        subjects = {}
        for text, href in items:
            combined = f"{text} {href}".lower()
            for subject, keywords in SUBJECT_KEYWORDS.items():
                if any(kw in combined for kw in keywords):
                    subjects[subject] = subjects.get(subject, 0) + 1
        return subjects
    
    def _group_by_subject(self, events: list[dict], subjects: dict) -> dict:
        """Группирует события по предметам."""
        exam_schedule = {}
        for event in events:
            categories = event.get("categories", [])
            if any("экзамен" in c or "сессия" in c for c in categories):
                # Пытаемся определить предмет из названия
                title_lower = event.get("title", "").lower()
                detected_subject = None
                for subject, keywords in SUBJECT_KEYWORDS.items():
                    if any(kw in title_lower for kw in keywords):
                        detected_subject = subject
                        break
                
                if detected_subject:
                    if detected_subject not in exam_schedule:
                        exam_schedule[detected_subject] = []
                    exam_schedule[detected_subject].append(event)
        
        return exam_schedule
    
    def _build_study_plan(self, exam_schedule: dict, today: date) -> list[dict]:
        """Строит учебный план на основе даты экзаменов."""
        plan = []
        
        for subject, events in sorted(exam_schedule.items()):
            if not events:
                continue
            
            # Берём ближайший экзамен по этому предмету
            nearest = min(events, key=lambda e: e.get("days_until", 999))
            days_until = nearest.get("days_until", 0)
            exam_date = nearest.get("date", today)
            
            # Определяем интенсивность подготовки
            if days_until <= 3:
                urgency = "urgent"
                emoji = "🔴"
            elif days_until <= 7:
                urgency = "week"
                emoji = "🟡"
            else:
                urgency = "month"
                emoji = "🟢"
            
            tips = PREP_TIPS.get(urgency, [])
            
            plan.append({
                "subject": subject,
                "exam_date": exam_date.strftime("%d.%m.%Y"),
                "days_until": days_until,
                "urgency": urgency,
                "emoji": emoji,
                "tips": tips,
            })
        
        # Сортируем по срочности
        plan.sort(key=lambda x: (x["days_until"], x["subject"]))
        return plan
    
    def format_study_tips(self, analysis: dict) -> str:
        """Форматирует анализ в красивый вывод для бота."""
        import html as html_mod
        esc = html_mod.escape
        bq = lambda body: f"<blockquote expandable>{body}</blockquote>"
        
        lines = ["<b>🎓 Умный учебный помощник</b>", ""]
        
        study_plan = analysis.get("study_plan", [])
        subjects = analysis.get("subjects", {})
        
        # Если есть план подготовки - выводим его
        if study_plan:
            lines.append("<b>📖 План подготовки:</b>")
            for item in study_plan:
                subject = esc(item["subject"])
                date_str = item["exam_date"]
                days = item["days_until"]
                emoji = item["emoji"]
                
                when = "СЕГОДНЯ!" if days == 0 else ("ЗАВТРА!" if days == 1 else f"через {days} дн.")
                tip_text = ""
                tips = item.get("tips", [])
                if tips:
                    tip_text = f"\n   💡 {esc(tips[0])}"
                
                lines.append(
                    f"{emoji} <b>{subject}</b> {date_str}\n"
                    f"   ⏰ {when}{tip_text}"
                )
            lines.append("")
        
        # Если есть обнаруженные предметы - выводим их
        if subjects:
            lines.append("<b>📚 Обнаруженные предметы в расписании:</b>")
            for subject, count in sorted(subjects.items(), key=lambda x: -x[1])[:6]:
                lines.append(f"• {esc(subject)}: {count} ссылок")
        else:
            lines.append(bq("📚 Явных данных о предметах не найдено."))
        
        return "\n".join(lines)
    
    def get_quick_tips(self, subject: str, days_until: int) -> list[str]:
        """Возвращает быстрые советы для конкретного предмета."""
        if days_until <= 3:
            urgency = "urgent"
        elif days_until <= 7:
            urgency = "week"
        else:
            urgency = "month"
        
        base_tips = PREP_TIPS.get(urgency, [])
        
        # Добавляем специфичные советы в зависимости от предмета
        subject_tips = {
            "math": "🔢 Фокусируйся на доказательствах и выводах формул",
            "programming": "💻 Пиши больше кода, даже если медленно",
            "physics": "⚛️ Разбирайся с физическим смыслом, не только формулами",
            "chemistry": "⚗️ Учи названия реакций и механизмы",
            "english": "🗣️ Говори вслух, слушай native speakers",
            "databases": "🗄️ Пиши SQL запросы на практику",
            "web": "🌐 Делай маленькие проекты на практику",
            "ai": "🤖 Изучи математику за ML, потом код",
            "systems": "⚙️ Рисуй диаграммы архитектуры",
        }
        
        subject_tip = subject_tips.get(subject)
        if subject_tip:
            return [subject_tip] + base_tips[:3]
        
        return base_tips
