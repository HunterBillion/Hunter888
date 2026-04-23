from app.api.health import _release_info


def test_release_info_reads_deploy_environment(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    monkeypatch.setenv("RELEASE_SHA", "abc123")
    monkeypatch.setenv("BUILD_TIME", "2026-04-23T12:00:00Z")

    assert _release_info() == {
        "service": "ai-trainer-api",
        "version": "9.9.9",
        "release_sha": "abc123",
        "build_time": "2026-04-23T12:00:00Z",
    }
