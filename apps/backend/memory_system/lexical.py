"""Local content recall when semantic embeddings are unavailable.

BM25-style lexical ranking + importance + recency. CJK bigrams avoid a model
download; unrelated queries return nothing. Persistent categories remain intact.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import UTC, datetime

_WORDS = re.compile(r"[a-z0-9_]+(?:\.[a-z0-9_]+)*|[\u3400-\u9fff]+", re.I)


def tokens(text: str) -> list[str]:
    result = []
    for word in _WORDS.findall(text[:20000].lower()):
        if "\u3400" <= word[0] <= "\u9fff":
            result.extend(word[i:i + 2] for i in range(len(word) - 1))
        elif len(word) > 1:
            result.append(word)
    return result


def rank_rows(rows, query: str, top_k: int, now: datetime):
    query_tokens = set(tokens(query))
    if not query_tokens or not rows:
        return []
    corpus = [Counter(tokens(row["content"])) for row in rows]
    average = sum(sum(doc.values()) for doc in corpus) / len(corpus) or 1
    document_frequency = Counter(term for doc in corpus for term in doc)
    scored = []
    for row, doc in zip(rows, corpus, strict=True):
        score = 0.0
        length = sum(doc.values())
        for term in query_tokens & doc.keys():
            idf = math.log(1 + (len(rows) - document_frequency[term] + 0.5) /
                           (document_frequency[term] + 0.5))
            score += idf * doc[term] * 2.2 / (doc[term] + 1.2 * (0.4 + 0.6 * length / average))
        if score <= 0:
            continue
        created = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        age_days = max(0, (now - created).total_seconds() / 86400)
        # A recency tie-breaker never erases stable long-term facts/preferences.
        score *= (0.5 + float(row["importance"] or 0.5)) * (0.5 + 0.5 * 2 ** (-age_days / 30))
        scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    seen = set()
    result = []
    for score, row in scored:
        key = row["content"].strip().casefold()
        if score < scored[0][0] * 0.25 or key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result) >= top_k:
            break
    return result
