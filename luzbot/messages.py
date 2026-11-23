"""User-facing Telegram texts (Spanish and English) and formatting helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TEXTS: dict[str, dict[str, str]] = {
    "es": {
        "monitor_started": "✅ Monitoreo activo: recibí el primer latido de casa ({time}).",
        "outage": (
            "🔴 Sin señal de casa\nÚltimo latido: {last}\nPosible corte de luz (o de internet)."
        ),
        "restored": (
            "🟢 Volvió la señal en casa\nHora: {now}\nEstuvo caída: {duration} (desde {start})"
        ),
        "unplugged": (
            "⚠️ El dispositivo de casa reporta que no está cargando, "
            "pero sigue habiendo internet.\n"
            "¿Se desenchufó, o el router está en una UPS?"
        ),
        "replugged": "🔌 El dispositivo de casa volvió a cargar.",
        "status_online": "🟢 Casa en línea\nÚltimo latido: hace {ago} ({last})",
        "status_offline": "🔴 Sin señal de casa desde {start} (hace {ago})",
        "status_unknown": "⏳ Todavía no recibo ningún latido de casa.",
        "stats_30d": "Últimos 30 días: {count} corte(s), {total} en total.",
        "history_header": "Últimos cortes:",
        "history_empty": "No hay cortes registrados. 🎉",
        "history_item": "• {start} → {end} ({duration})",
        "ongoing": "en curso",
        "help": ("Comandos:\n/estado — estado actual\n/historial — últimos cortes"),
        "less_than_minute": "menos de 1 min",
    },
    "en": {
        "monitor_started": "✅ Monitoring active: got the first heartbeat from home ({time}).",
        "outage": (
            "🔴 No signal from home\nLast heartbeat: {last}\nPossible power (or internet) outage."
        ),
        "restored": (
            "🟢 Home is back online\nTime: {now}\nOutage lasted: {duration} (since {start})"
        ),
        "unplugged": (
            "⚠️ The home device reports it is not charging, "
            "but the internet is still up.\n"
            "Was it unplugged, or is the router on a UPS?"
        ),
        "replugged": "🔌 The home device is charging again.",
        "status_online": "🟢 Home is online\nLast heartbeat: {ago} ago ({last})",
        "status_offline": "🔴 No signal from home since {start} ({ago} ago)",
        "status_unknown": "⏳ No heartbeat received from home yet.",
        "stats_30d": "Last 30 days: {count} outage(s), {total} in total.",
        "history_header": "Recent outages:",
        "history_empty": "No outages recorded. 🎉",
        "history_item": "• {start} → {end} ({duration})",
        "ongoing": "ongoing",
        "help": ("Commands:\n/status — current status\n/history — recent outages"),
        "less_than_minute": "less than 1 min",
    },
}

SUPPORTED_LANGUAGES = tuple(TEXTS)

TIME_FORMAT = "%d/%m %H:%M"


class Messages:
    """Renders texts in one language, formatting times in one timezone."""

    def __init__(self, language: str = "es", timezone: ZoneInfo | None = None) -> None:
        if language not in TEXTS:
            raise ValueError(f"unsupported language: {language!r}")
        self.language = language
        self.timezone = timezone or ZoneInfo("UTC")
        self._texts = TEXTS[language]

    def __call__(self, key: str, **values: object) -> str:
        return self._texts[key].format(**values)

    def time(self, timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp, self.timezone).strftime(TIME_FORMAT)

    def duration(self, seconds: float) -> str:
        total = int(seconds)
        if total < 60:
            return self._texts["less_than_minute"]
        days, rest = divmod(total, 86_400)
        hours, rest = divmod(rest, 3_600)
        minutes = rest // 60
        parts = []
        if days:
            parts.append(f"{days} d")
        if hours:
            parts.append(f"{hours} h")
        if minutes:
            parts.append(f"{minutes} min")
        return " ".join(parts)
