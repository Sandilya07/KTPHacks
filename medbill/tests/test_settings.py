from api.settings import Settings, load_environment


def test_env_file_loads_at_startup(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DEMO_MODE=0\nANTHROPIC_API_KEY=test-key\n", encoding="utf-8")
    load_environment(env_file)
    import os
    assert not Settings().demo_mode
    assert os.environ["ANTHROPIC_API_KEY"] == "test-key"


def test_explicit_environment_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    env_file = tmp_path / ".env"
    env_file.write_text("DEMO_MODE=0\n", encoding="utf-8")
    load_environment(env_file)
    assert Settings().demo_mode
