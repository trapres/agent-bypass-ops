"""Remove benchmark framing without sanitizing submissions under test."""

from pathlib import Path

import pytest

from abo.prompts import user_prompt
from abo.submission import Submission, load_cases

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("corpus", [
    "cases", "bypass-cases", "family-cases", "tob-cases",
    "bypass-cases-expanded", "family-cases-expanded", "tob-cases-expanded",
])
@pytest.mark.parametrize("mode", ["oneshot", "agent"])
def test_loaded_cases_hide_benchmark_metadata_and_preserve_content(corpus, mode):
    for case in load_cases(ROOT / corpus):
        submission = case.submission
        prompt = user_prompt(submission, mode)
        metadata = submission.metadata_block()
        assert "submission_id:" not in metadata
        assert "source:" not in metadata
        assert submission.source not in prompt
        assert case.id not in metadata
        assert submission.diff.rstrip("\n") in prompt
        for content in (submission.title, submission.author, submission.description):
            if content:
                assert content in metadata


def test_real_submission_metadata_is_unchanged():
    submission = Submission(id="repo@123", diff="patch", source="repo:HEAD", title="subject")
    assert "submission_id: repo@123" in submission.metadata_block()
    assert "source: repo:HEAD" in submission.metadata_block()


def test_missing_tree_description_does_not_reveal_fixture_provenance():
    # The diff-only baseline fixtures must be blind in agent mode too.
    for case in load_cases(ROOT / "cases"):
        assert "fixture" not in case.submission.workspace.describe().lower()
