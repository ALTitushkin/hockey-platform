"""Scenario-specific publication windows. Migration never grants permission to publish."""

from datetime import datetime, time, timedelta, timezone

MSK = timezone(timedelta(hours=3))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def classify(draft: dict, kind: str, now: datetime | None = None) -> tuple[str, list[str]]:
    now = now or utcnow()
    if now.tzinfo is None:
        raise ValueError("Lifecycle requires aware time")
    closed = draft.get("editorial_closed")
    if closed:
        return "closed", [closed.get("reason", "закрыто редактором")]
    data = draft.get("data") or {}
    if not isinstance(data, dict):
        return "blocked", ["неверная схема данных"]
    if kind.startswith("story-"):
        source = data.get("source_snapshot")
        if not isinstance(source, dict) or not source.get("content_hash"):
            return "legacy_review", ["исторический материал без версии источника; нужна новая проверка"]
    try:
        if kind in ("night", "league", "weekly"):
            day = datetime.strptime(draft["date"], "%Y-%m-%d").date()
            if now.astimezone(MSK).date() < day:
                return "scheduled", ["дата выпуска ещё не наступила"]
            deadline = datetime.combine(day + timedelta(days=7 if kind == "weekly" else 1), time.min, MSK)
        elif kind == "tonight":
            starts = [datetime.fromisoformat(g["start"].replace("Z", "+00:00")) for g in data.get("games", [])]
            if not starts or any(start.tzinfo is None for start in starts):
                return "needs_revalidation", ["анонс без подтверждённого времени начала матчей"]
            deadline = min(starts)
        elif kind.startswith("story-"):
            event = data.get("event_revision") or {}
            if data.get("expires_at"):
                deadline = datetime.fromisoformat(data["expires_at"])
                if deadline.tzinfo is None:
                    raise ValueError("expiry needs timezone")
            elif event.get("family") == "signing" and event.get("complete") is True:
                return "ready", []  # Confirmed signing is not a forecast with an arbitrary TTL.
            else:
                return "needs_revalidation", ["актуальность события не подтверждена для отправки"]
        else:
            return "ready", []
        if data.get("expires_at"):
            explicit = datetime.fromisoformat(data["expires_at"])
            if explicit.tzinfo is None:
                raise ValueError("expiry needs timezone")
            deadline = min(deadline, explicit)
    except (KeyError, ValueError, TypeError, AttributeError):
        return "blocked", ["неверная дата или окно публикации"]
    if now >= deadline:
        return "expired", ["окно публикации этого сценария закрыто"]
    return "ready", []
