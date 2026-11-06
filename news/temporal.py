"""Conservative check for dated injury history presented as a fresh injury."""
import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def check(text, story, names):
    issues = []
    for pid, english in story.en.items():
        rec = names.get(str(pid))
        if not rec:
            continue
        # Bind the injury and its date to the named subject, not another paragraph.
        match = re.search(re.escape(english) +
                          r",?\s+(?:who\s+)?(?:sustained|suffered|was injured)"
                          r"[^.;\n]{0,100}?\b(" + "|".join(MONTHS) +
                          r")[a-z]*\.?\s+(\d{1,2})\b", story.text, re.I)
        if not match:
            continue
        try:
            injured = date(story.date.year, MONTHS[match[1].lower()[:3]], int(match[2]))
            if injured > story.date.date():
                injured = injured.replace(year=injured.year - 1)
        except ValueError:
            continue
        if (story.date.date() - injured).days <= 2:
            continue
        for clause in re.split(r"[.!?\n]|,?\s+а\s+", text):
            if rec["surname"].lower().replace("ё", "е") not in clause.lower().replace("ё", "е"):
                continue
            if (re.search(r"\b(?:выбыл|получил\w* (?:травм|поврежден)|травмировал\w*)", clause, re.I)
                    and not re.search(r"продолжа|ранее|по-прежнему|ещ[её] |\b\d{1,2}\s+"
                                      r"(?:январ|феврал|март|апрел|ма[яй]|июн|июл|август|"
                                      r"сентябр|октябр|ноябр|декабр)", clause, re.I)):
                issues.append("старая травма подана как новая: " + rec["surname"])
    return issues
