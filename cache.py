"""A dict that keeps only its newest entries, for the archive modules' response caches.

The server runs for days on Cloud Run with 512 MiB or so: an unbounded cache (one loc.gov search
answer is ~2 MB of JSON, one landmark report several hundred KB of text) grows with every question
until the instance runs out of memory and drops the run in progress."""


class BoundedCache(dict):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        while len(self) > self.limit:
            del self[next(iter(self))]  # the oldest entry
