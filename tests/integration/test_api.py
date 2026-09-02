from forestfix.api.app import create_app


def test_api_exposes_health_and_safe_patch_inspection() -> None:
    app = create_app()
    routes = {route.path: route for route in app.routes}

    assert "/health" in routes
    assert "/inspect-patch" in routes
    assert routes["/health"].endpoint() == {"status": "ok", "service": "forestfix"}

    response = routes["/inspect-patch"].endpoint(
        {
            "patch": "--- a/parser.py\n+++ b/parser.py\n@@ -1 +1 @@\n-old\n+new\n",
            "allowed_paths": ["parser.py"],
            "denied_paths": [],
        }
    )
    assert response["accepted"] is False
    assert response["findings"][0]["code"] == "MALFORMED_PATCH"
