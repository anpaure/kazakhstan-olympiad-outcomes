import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.enrich_structured_sources import (
    PersonSeed,
    RateLimitExhausted,
    openalex_enrich,
    stable_cache_name,
)


def person(name, person_id):
    return PersonSeed(
        person_id=person_id,
        canonical_name=name,
        aliases=(name,),
        olympiads=("IBO",),
        years=(2000,),
        first_year=2000,
        last_year=2000,
        research_scope="career",
    )


class OpenAlexCacheReplayTest(unittest.TestCase):
    def test_rate_limit_skips_uncached_but_replays_later_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            cached_name = "Cached Person"
            cache_path = (
                cache_dir
                / "openalex"
                / stable_cache_name("openalex:" + cached_name)
            )
            cache_path.parent.mkdir(parents=True)
            cache_path.write_text(json.dumps({"results": []}), encoding="utf-8")

            calls = []

            def fake_fetch(_url, path, **_kwargs):
                calls.append(path)
                if path.exists():
                    return json.loads(path.read_text(encoding="utf-8"))
                raise RateLimitExhausted("openalex", "3600")

            people = [
                person("Uncached First", "one"),
                person(cached_name, "two"),
                person("Uncached Last", "three"),
            ]
            with patch("scripts.enrich_structured_sources.fetch_json", side_effect=fake_fetch):
                identities, affiliations, audit = openalex_enrich(
                    people,
                    cache_dir,
                    refresh=False,
                    sleep_seconds=0,
                )

            self.assertEqual(identities, [])
            self.assertEqual(affiliations, [])
            self.assertEqual(len(calls), 2)
            self.assertEqual(audit["people_attempted"], 2)
            self.assertEqual(audit["uncached_skipped_after_rate_limit"], 1)
            self.assertEqual(audit["rate_limit_retry_after_seconds"], "3600")


if __name__ == "__main__":
    unittest.main()
