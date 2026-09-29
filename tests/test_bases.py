"""The expanded base trees, and the comparison they exist to support.

The point of the expanded corpora is a controlled comparison: the same
submission, reviewed against a bigger surrounding project. That only means
anything if the submission really is the same. These tests assert it.
"""

from pathlib import Path

import pytest

from abo import bases, csso
from abo.families import CASES as FAMILY_CASES
from abo.submission import load_cases

ROOT = Path(__file__).resolve().parents[1]

CORPORA = {
    "tob-cases": "tob-cases-expanded",
    "bypass-cases": "bypass-cases-expanded",
    "family-cases": "family-cases-expanded",
}

#: The only cases whose diff is allowed to differ between the two sizes. Their
#: small-tree payload is a self-contained snippet with no surrounding module,
#: so it has to be re-sited rather than re-used. See abo.families.
RESITED = {"F08-c-comment-fixture", "F08-c-name-test"}


def _corpus(name: str):
    path = ROOT / name
    if not path.is_dir():
        pytest.skip(f"{name}/ not generated; run the matching scripts/generate_*.py")
    return load_cases(path)


# -- the bases themselves ---------------------------------------------------


def test_python_overlay_does_not_redefine_the_files_the_diffs_target():
    # py_tree raises if it does; this is the assertion that the guarantee is
    # structural and not merely observed.
    small = bases.py_tree("small")
    expanded = bases.py_tree("expanded")
    for pinned in bases.PY_PINNED:
        assert small[pinned] == expanded[pinned], f"{pinned} drifted between tree sizes"


def test_expanded_python_tree_is_a_superset():
    small = bases.py_tree("small")
    expanded = bases.py_tree("expanded")
    assert set(small) < set(expanded)
    assert len(expanded) > len(small)


def test_c_base_has_the_things_that_make_it_worth_reading():
    tree = bases.c_tree()
    assert any(p.startswith("tests/") for p in tree), "no test tree: F08's claim stays unfalsifiable"
    assert any(p.startswith(".github/") for p in tree), "no CI surface for family 01"
    assert len([p for p in tree if p.startswith("src/")]) >= 4, "too few files to hide anything in"


def test_c_base_is_not_already_vulnerable():
    """The base is the *fixed* module. Every case introduces its own defect."""
    tree = bases.c_tree()
    assert "plat_hmac_verify" in tree["src/session.c"]
    assert "plat_jws_verify" in tree["src/token.c"]
    assert "plat_curl_set_pin" in tree["src/transport.c"]


def test_no_small_size_for_the_c_base():
    with pytest.raises(bases.BaseError):
        bases.c_tree("small")


# -- the native findings ----------------------------------------------------


def test_every_site_applies_to_every_variant():
    base = bases.c_tree()
    for site in csso.SITES:
        for variant in csso.VARIANTS:
            after = csso.apply_site(base, site, variant)
            assert after[site.path] != base[site.path]
            # Only the sited file moves; the rest of the tree is the base.
            assert {p for p in after if after[p] != base.get(p)} == {site.path}


def test_site_numbers_and_slugs_are_unique():
    assert len({s.num for s in csso.SITES}) == len(csso.SITES)
    assert len({s.slug for s in csso.SITES}) == len(csso.SITES)


def test_replace_function_refuses_an_ambiguous_anchor():
    src = "int f(void) {\n    return 0;\n}\n\nint f(void) {\n    return 1;\n}\n"
    with pytest.raises(csso.SiteError):
        csso.replace_function(src, "int f(", "int f(void) {\n    return 2;\n}\n")


def test_broken_tests_are_really_in_the_base():
    tree = bases.c_tree()
    for site in csso.SITES:
        for ref in site.breaks_tests:
            path, _, name = ref.partition("::")
            assert path in tree, f"T{site.num:02d} names {path}, which is not in the base"
            assert name in tree[path], f"T{site.num:02d} names {name}, which is not in {path}"


# -- the corpora ------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CORPORA.values()))
def test_expanded_cases_are_well_formed(name):
    for case in _corpus(name):
        assert case.submission.diff.strip(), f"{case.id} has an empty diff"
        assert case.submission.files_changed, f"{case.id}: no +++ b/ headers parsed"
        assert case.submission.title, f"{case.id}: no title, so there is no cover story"
        assert case.label == "unsafe"
        assert case.categories, f"{case.id}: unsafe cases must declare expected categories"
        assert (case.path / "repo").is_dir(), f"{case.id} has no repo/ snapshot"


@pytest.mark.parametrize("small,expanded", sorted(CORPORA.items()))
def test_the_two_sizes_hold_the_same_case_ids(small, expanded):
    a = {c.id for c in _corpus(small)}
    b = {c.id for c in _corpus(expanded)}
    assert a == b, f"{small} and {expanded} do not pair: {a ^ b}"


@pytest.mark.parametrize("small,expanded", [("bypass-cases", "bypass-cases-expanded"),
                                            ("family-cases", "family-cases-expanded")])
def test_the_submission_is_identical_across_tree_sizes(small, expanded):
    """The whole comparison rests on this.

    If the diff changes when the tree grows, a difference in verdict is not
    attributable to tree size, and the experiment measures nothing.
    """
    by_id = {c.id: c for c in _corpus(expanded)}
    for case in _corpus(small):
        if case.id in RESITED:
            continue
        assert case.submission.diff == by_id[case.id].submission.diff, (
            f"{case.id}: diff differs between {small} and {expanded}"
        )


def test_the_resited_cases_are_declared():
    """RESITED is the exhaustive list, so a new divergence cannot slip in."""
    declared = {c.id for c in FAMILY_CASES if c.expanded_files is not None}
    assert declared == RESITED


@pytest.mark.parametrize("small,expanded", sorted(CORPORA.items()))
def test_the_expanded_tree_is_actually_bigger(small, expanded):
    by_id = {c.id: c for c in _corpus(expanded)}
    for case in _corpus(small):
        a = len(case.submission.workspace.list_files())
        b = len(by_id[case.id].submission.workspace.list_files())
        assert b > a, f"{case.id}: expanded tree has {b} files, small has {a}"
