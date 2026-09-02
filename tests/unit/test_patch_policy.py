from pathlib import Path

from forestfix.policy.patch_policy import inspect_patch

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "parser_bug"

SAFE_PATCH = """diff --git a/src/parser/core.py b/src/parser/core.py
index 1111111..2222222 100644
--- a/src/parser/core.py
+++ b/src/parser/core.py
@@ -1 +1 @@
-return False
+return True
"""


def test_patch_in_allowed_scope_has_no_findings() -> None:
    findings = inspect_patch(
        SAFE_PATCH,
        allowed_patterns=("src/parser/**", "tests/test_parser.py"),
        denied_patterns=("pyproject.toml", ".github/**"),
    )

    assert findings == ()


def test_patch_outside_allowed_scope_is_rejected() -> None:
    patch = SAFE_PATCH.replace("src/parser/core.py", "pyproject.toml")

    findings = inspect_patch(
        patch,
        allowed_patterns=("src/parser/**", "tests/test_parser.py"),
        denied_patterns=("pyproject.toml", ".github/**"),
    )

    assert [finding.code for finding in findings] == ["DENIED_PATH"]
    assert findings[0].path == "pyproject.toml"


def test_patch_adding_test_skip_is_rejected() -> None:
    patch = """diff --git a/tests/test_parser.py b/tests/test_parser.py
--- a/tests/test_parser.py
+++ b/tests/test_parser.py
@@ -1,2 +1,3 @@
+@pytest.mark.skip(reason=\"agent could not fix it\")
 def test_parser():
     assert parse(\"x\")
"""

    findings = inspect_patch(
        patch,
        allowed_patterns=("src/parser/**", "tests/test_parser.py"),
        denied_patterns=("pyproject.toml",),
    )

    assert [finding.code for finding in findings] == ["TEST_CHEATING"]
    assert findings[0].path == "tests/test_parser.py"


def test_patch_without_git_file_headers_is_rejected() -> None:
    findings = inspect_patch(
        "--- a/parser.py\n+++ b/parser.py\n@@ -1 +1 @@\n-old\n+new\n",
        allowed_patterns=("parser.py",),
        denied_patterns=(),
    )

    assert [finding.code for finding in findings] == ["MALFORMED_PATCH"]


def test_bundled_top_level_test_cheating_patch_is_rejected() -> None:
    patch = (FIXTURE_ROOT / "patches" / "cheating.patch").read_text()

    findings = inspect_patch(
        patch,
        allowed_patterns=("parser.py", "test_parser.py"),
        denied_patterns=(),
    )

    assert "TEST_CHEATING" in {finding.code for finding in findings}


def test_rename_from_denied_source_is_rejected() -> None:
    patch = """diff --git a/secrets.txt b/src/secrets.txt
similarity index 100%
rename from secrets.txt
rename to src/secrets.txt
"""

    findings = inspect_patch(
        patch,
        allowed_patterns=("src/**",),
        denied_patterns=("secrets.txt",),
    )

    assert "DENIED_PATH" in {finding.code for finding in findings}
    assert "secrets.txt" in {finding.path for finding in findings}
