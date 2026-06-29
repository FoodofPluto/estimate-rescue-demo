import importlib
import inspect


def load_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "routing.db"))
    import config
    import storage

    importlib.reload(config)
    importlib.reload(storage)
    import app

    return importlib.reload(app)


def test_public_response_route_is_claimed_before_operator_navigation(tmp_path, monkeypatch):
    app = load_app(tmp_path, monkeypatch)
    rendered = []
    monkeypatch.setattr(app, "customer_response_page", rendered.append)

    assert app.render_public_response_route({"customer_response_token": "valid-token"}) is True
    assert rendered == ["valid-token"]
    assert app.render_public_response_route({}) is False


def test_operator_customer_response_screen_is_only_link_management(tmp_path, monkeypatch):
    app = load_app(tmp_path, monkeypatch)

    assert "Customer Response Page" not in app.PAGES
    operator_source = inspect.getsource(app.customer_response_link_page)
    assert "customer_response_page" not in operator_source
    assert "missing a token" not in operator_source
