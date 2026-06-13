"""
Парсер расписания с fmi.usm.md, кэш и сохранение последних данных.
При недоступности сайта отдаётся последнее успешное сохранение.
"""
import html
import json
import logging
import os
import time
from copy import deepcopy
from threading import Lock
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from analyzer import SmartAnalyzer

logger = logging.getLogger(__name__)

URLS = [
    "https://fmi.usm.md",
    "https://fmi.usm.md/orar/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

NO_PROXIES = {"http": None, "https": None}
CACHE_REFRESH_SECONDS = 1800
SHORT_LIMIT = 15
REQUEST_TIMEOUT = 10  # Жёсткий timeout для всех запросов
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_snapshot.json")

_cache_lock = Lock()
_analyzer = SmartAnalyzer()

cached_data: dict = {
    "short": "⏳ Загружаю данные, подождите немного...",
    "full": "⏳ Загружаю данные, подождите немного...",
    "items": [],
    "analysis": {},
    "last_upd": "—",
    "last_upd_ts": 0,
    "error": None,
    "from_saved": False,
}

_last_good: dict = {
    "items": [],
    "short": "",
    "full": "",
    "analysis": {},
    "last_upd": "—",
    "last_upd_ts": 0,
}

def _esc(text: str) -> str:
    return html.escape(text or "")

def _blockquote(body: str) -> str:
    return f"<blockquote expandable>{body}</blockquote>"

def _normalize_href(href: str, base_url: str) -> str:
    href = href.strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return urljoin(base_url, href)
    return href

def _parse_links_from_page(url: str) -> list[tuple[str, str]]:
    """
    Парсит ссылки со страницы с жёстким timeout=10 секунд.
    Если сайт не отвечает за 10 секунд - выбросит исключение.
    """
    resp = requests.get(url, headers=HEADERS, proxies=NO_PROXIES, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items: list[tuple[str, str]] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        href = _normalize_href(link.get("href", ""), url)
        text = link.get_text(strip=True) or ""
        if not href or len(text) < 3:
            continue
        lower = href.lower()
        if any(x in lower for x in ["orar", ".pdf", "docs.google", "spreadsheets"]):
            if href not in seen:
                seen.add(href)
                items.append((text[:80], href))
    return items

def fetch_all_items() -> tuple[list[tuple[str, str]], Optional[str]]:
    """
    Попытается загрузить ссылки со всех сайтов.
    Если сайт не отвечает за REQUEST_TIMEOUT секунд - переходит к следующему.
    Если ничего не загрузилось - отдаёт ошибку.
    """
    all_items: list[tuple[str, str]] = []
    seen: set[str] = set()
    errors: list[str] = []
    for url in URLS:
        try:
            page_items = _parse_links_from_page(url)
            for text, href in page_items:
                if href not in seen:
                    seen.add(href)
                    all_items.append((text, href))
        except requests.Timeout:
            logger.error("Timeout при парсинге %s (>%d сек)", url, REQUEST_TIMEOUT)
            errors.append(f"{url}: timeout (>{REQUEST_TIMEOUT}s)")
        except requests.ConnectionError as exc:
            logger.error("Ошибка соединения %s: %s", url, exc)
            errors.append(f"{url}: connection error")
        except Exception as exc:
            logger.error("Ошибка парсинга %s: %s", url, exc)
            errors.append(f"{url}: {exc}")
    if not all_items and errors:
        return [], "; ".join(errors)
    return all_items, "; ".join(errors) if errors else None

def _format_short(items: list[tuple[str, str]]) -> str:
    if not items:
        body = _esc("Расписание не найдено. Сайт: https://fmi.usm.md/orar/")
        return f"<b>📍 Краткое расписание</b>\n\n{_blockquote(body)}"
    content = "\n".join(f"• {_esc(t)}\n  {_esc(h)}" for t, h in items[:SHORT_LIMIT])
    return f"<b>📍 Краткое расписание</b>\n\n{_blockquote(content)}"

def _format_full(items: list[tuple[str, str]]) -> str:
    if not items:
        body = _esc("Расписание не найдено. https://fmi.usm.md/orar/")
        return f"<b>📚 Полный список ссылок</b>\n\n{_blockquote(body)}"
    content = "\n".join(f"• {_esc(t)}\n  {_esc(h)}" for t, h in items)
    if len(content) > 3800:
        content = content[:3800] + "\n...(обрезано)"
    return f"<b>📚 Полный список ссылок</b>\n\n{_blockquote(content)}"

def _apply_success(items: list[tuple[str, str]], error: Optional[str]) -> None:
    now_str = time.strftime("%H:%M:%S")
    short = _format_short(items)
    full = _format_full(items)
    analysis = _analyzer.analyze(items)
    cached_data["items"] = items
    cached_data["short"] = short
    cached_data["full"] = full
    cached_data["analysis"] = analysis
    cached_data["last_upd"] = now_str
    cached_data["last_upd_ts"] = time.time()
    cached_data["error"] = error
    cached_data["from_saved"] = False
    _last_good["items"] = items
    _last_good["short"] = short
    _last_good["full"] = full
    _last_good["analysis"] = analysis
    _last_good["last_upd"] = now_str
    _last_good["last_upd_ts"] = cached_data["last_upd_ts"]
    _save_disk_cache()

def _restore_from_saved() -> bool:
    if not _last_good.get("items"):
        return False
    cached_data["items"] = _last_good["items"]
    cached_data["short"] = _last_good["short"]
    cached_data["full"] = _last_good["full"]
    cached_data["analysis"] = deepcopy(_last_good.get("analysis", {}))
    cached_data["last_upd"] = _last_good["last_upd"]
    cached_data["last_upd_ts"] = _last_good["last_upd_ts"]
    cached_data["from_saved"] = True
    return True

def _save_disk_cache() -> None:
    try:
        payload = {
            "items": _last_good["items"],
            "short": _last_good["short"],
            "full": _last_good["full"],
            "analysis": _last_good["analysis"],
            "last_upd": _last_good["last_upd"],
            "last_upd_ts": _last_good["last_upd_ts"],
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as exc:
        logger.warning("Не удалось сохранить cache_snapshot.json: %s", exc)

def _load_disk_cache() -> None:
    if not os.path.isfile(CACHE_FILE):
        return
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("items"):
            _last_good.update(data)
            _restore_from_saved()
            logger.info(
                "Загружено сохранение с диска (%d ссылок, %s)",
                len(_last_good["items"]),
                _last_good.get("last_upd"),
            )
    except Exception as exc:
        logger.warning("Не удалось прочитать cache_snapshot.json: %s", exc)

def update_cache() -> bool:
    items, error = fetch_all_items()
    if not items:
        cached_data["error"] = error
        if _restore_from_saved():
            logger.warning("Сайт недоступен, отдано сохранённое: %s", error)
            return False
        cached_data["short"] = _format_short([])
        cached_data["full"] = cached_data["short"]
        logger.warning("Кэш не обновлён: %s", error)
        return False
    _apply_success(items, error)
    logger.info("Кэш обновлён в %s (%d ссылок)", cached_data["last_upd"], len(items))
    return True

def refresh_on_request() -> str:
    with _cache_lock:
        ok = update_cache()
        if ok:
            return f"🕒 Обновлено: {cached_data['last_upd']}"
        if cached_data.get("from_saved"):
            err = cached_data.get("error") or "сайт недоступен"
            return (
                f"⚠️ Сайт не ответил ({_esc(str(err))[:120]}). "
                f"Показано сохранённое от {cached_data['last_upd']}."
            )
        return "❌ Нет сохранённых данных. Попробуйте позже."

def update_cache_loop() -> None:
    """
    Главный цикл обновления кэша. Обёрнут в try-except, чтобы 
    бот не падал при критических ошибках парсинга.
    """
    _load_disk_cache()
    
    try:
        update_cache()
    except Exception as exc:
        logger.exception("Критическая ошибка при инициализации кэша: %s", exc)
    
    while True:
        time.sleep(CACHE_REFRESH_SECONDS)
        try:
            with _cache_lock:
                update_cache()
        except Exception as exc:
            logger.exception("Критическая ошибка в цикле обновления кэша: %s", exc)
            # Продолжаем работу, перейдём к следующему циклу

def get_raspisanie_text() -> tuple[str, str]:
    footer = refresh_on_request()
    return cached_data["short"], footer

def get_orar_text() -> tuple[str, str]:
    footer = refresh_on_request()
    return cached_data["full"], footer

def get_smart_report() -> str:
    analysis = cached_data.get("analysis") or {}
    return _analyzer.format_report(analysis, cached_data.get("last_upd", "—"))

def get_status_text() -> str:
    ts = cached_data.get("last_upd_ts", 0)
    age_min = int((time.time() - ts) / 60) if ts else None
    age_str = f"{age_min} мин назад" if age_min is not None else "никогда"
    items_count = len(cached_data.get("items", []))
    saved_count = len(_last_good.get("items", []))
    err = cached_data.get("error")
    info = (
        f"🕒 Последнее обновление: {cached_data.get('last_upd', '—')} ({age_str})\n"
        f"🔗 Ссылок в кэше: {items_count}\n"
        f"💾 Сохранено на диске: {saved_count} ссылок\n"
        f"🔄 Автообновление: каждые {CACHE_REFRESH_SECONDS // 60} мин\n"
        f"⏳ Кулдаун команд: 30–45 сек\n"
        f"🔒 Локальный анализ, без внешних AI"
    )
    lines = ["<b>📊 Статус бота</b>", "", _blockquote(_esc(info))]
    if err:
        lines.append(f"\n⚠️ {_esc(str(err))}")
    if cached_data.get("from_saved"):
        lines.append("\n📦 Сейчас показаны сохранённые данные")
    return "\n".join(lines)
