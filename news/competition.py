"""Explicit competition/statistics scope. Unsupported profiles never inherit NHL rules."""

import re
from dataclasses import asdict, dataclass
from datetime import date


@dataclass(frozen=True)
class Profile:
    competition: str
    phase: str
    game_type: int | None
    label: str
    career_key: str | None
    version: int = 1


# API mappings only; overtime/series rules are deliberately not inferred here.
PROFILES = {
    "regular": Profile("nhl", "regular", 2, "регулярного чемпионата", "regularSeason"),
    "playoffs": Profile("nhl", "playoffs", 3, "плей-офф", "playoffs"),
    "preseason": Profile("nhl", "preseason", 1, "предсезонки", None),
}
PROFILE_REGISTRY = {(p.competition, p.phase): p for p in PROFILES.values()}


def register_profile(profile: Profile) -> None:
    """Adapters register typed profiles; changing an existing ruleset needs a new version/review."""
    if (not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", profile.competition)
            or not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", profile.phase)
            or type(profile.version) is not int or profile.version < 1):
        raise ValueError("Неверный профиль соревнования")
    key = (profile.competition, profile.phase)
    if key in PROFILE_REGISTRY and PROFILE_REGISTRY[key] != profile:
        raise ValueError("Профиль уже зарегистрирован: нельзя молча заменить правила")
    PROFILE_REGISTRY[key] = profile


@dataclass(frozen=True)
class Scope:
    edition: str
    phase: str = "regular"
    competition: str = "nhl"

    def __post_init__(self):
        if any(not isinstance(value, str) for value in (self.edition, self.phase, self.competition)):
            raise ValueError("Идентификаторы соревнования должны быть строками")
        if (self.competition, self.phase) not in PROFILE_REGISTRY:
            raise ValueError("Неподдержанное соревнование/стадия: нужен отдельный профиль")
        if self.competition == "nhl":
            if (len(self.edition) != 8 or not self.edition.isascii() or not self.edition.isdigit()
                    or int(self.edition[4:]) != int(self.edition[:4]) + 1):
                raise ValueError("Неверный розыгрыш: нужен сезон YYYYYYYY")
        elif not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", self.edition):
            raise ValueError("Неверный идентификатор розыгрыша")

    @property
    def profile(self) -> Profile:
        return PROFILE_REGISTRY[(self.competition, self.phase)]

    def data(self) -> dict:
        return {**asdict(self), "ruleset_version": self.profile.version}


def from_data(data: dict) -> Scope:
    """Validate persisted context, including the profile version."""
    scope = Scope(data["edition"], data["phase"], data["competition"])
    if data.get("ruleset_version") != scope.profile.version:
        raise ValueError("Неизвестная версия профиля")
    return scope


def edition_for(day: str) -> str:
    """NHL season naming boundary; this does not infer a competition's playing phase."""
    parsed = date.fromisoformat(day)
    year = parsed.year - (parsed.month < 7)
    return f"{year}{year + 1}"


def reports_scope(reports: list) -> dict | None:
    """No inferred scope for old/missing metadata or a mixed-stage collection."""
    if not reports or any(not report.scope for report in reports):
        return None
    first = reports[0].scope
    return first if all(report.scope == first for report in reports) else None
