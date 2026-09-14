"""Choose a separate URL Inspection rotation for each language site."""
from .core import LANGS, language


def select_inspection_urls(candidates, previous, priority, per_language=30):
    # Preserve the old rotation order within each language. Unused slots are
    # not transferred to other languages. At most 100 per language (900 total).
    limit = min(100, max(1, int(per_language)))
    buckets = {lg: [] for lg in LANGS}
    for url in set(candidates) | set(priority):
        lg = language(url)
        if lg in buckets:
            buckets[lg].append(url)
    selected = []
    for lg in LANGS:
        ranked = sorted(buckets[lg], key=lambda u: (
            u in previous, previous.get(u, {}).get('checked_at', ''),
            u not in priority, u))
        selected.extend(ranked[:limit])
    return selected
