from parser import normalize_header

assert normalize_header("  Content-Type  ") == "content-type"

try:
    normalize_header("   ")
except ValueError:
    pass
else:
    raise AssertionError("empty headers must be rejected")
