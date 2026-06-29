import importlib
import inspect
from types import SimpleNamespace


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


def test_settings_message_templates_is_not_operator_navigation(tmp_path, monkeypatch):
    app = load_app(tmp_path, monkeypatch)

    assert "Settings / Message Templates" not in app.PAGES
    assert not hasattr(app, "settings_page")


class SidebarStub:
    def __init__(self):
        self.radio_call = None

    def button(self, _label):
        return False

    def radio(self, label, options, index):
        self.radio_call = (label, options, index)
        return options[index]


def run_operator_navigation(app, monkeypatch, session_page, query_params=None):
    sidebar = SidebarStub()
    session_state = {"page": session_page}
    rendered = []
    pages = {
        "Public Demo Home": lambda: rendered.append("Public Demo Home"),
        "Customer Response": lambda: rendered.append("Customer Response"),
    }
    streamlit = SimpleNamespace(
        query_params=query_params or {},
        session_state=session_state,
        sidebar=sidebar,
        rerun=lambda: None,
    )
    monkeypatch.setattr(app, "st", streamlit)
    monkeypatch.setattr(app, "PAGES", pages)
    monkeypatch.setattr(app, "is_logged_in", lambda: False)

    app.main()
    return session_state, sidebar, rendered


def test_invalid_session_page_resets_to_safe_default(tmp_path, monkeypatch):
    app = load_app(tmp_path, monkeypatch)

    session_state, sidebar, rendered = run_operator_navigation(
        app, monkeypatch, "Removed Page"
    )

    assert session_state["page"] == "Public Demo Home"
    assert sidebar.radio_call == (
        "Navigation",
        ["Public Demo Home", "Customer Response"],
        0,
    )
    assert rendered == ["Public Demo Home"]


def test_removed_settings_session_page_resets_to_safe_default(tmp_path, monkeypatch):
    app = load_app(tmp_path, monkeypatch)

    session_state, sidebar, rendered = run_operator_navigation(
        app, monkeypatch, "Settings / Message Templates"
    )

    assert session_state["page"] == "Public Demo Home"
    assert "Settings / Message Templates" not in sidebar.radio_call[1]
    assert rendered == ["Public Demo Home"]


def test_legacy_public_page_query_does_not_crash_navigation(tmp_path, monkeypatch):
    app = load_app(tmp_path, monkeypatch)

    session_state, _sidebar, rendered = run_operator_navigation(
        app,
        monkeypatch,
        "Customer Response Page",
        {"page": "Customer Response Page"},
    )

    assert session_state["page"] == "Public Demo Home"
    assert rendered == ["Public Demo Home"]


def test_public_token_route_bypasses_sidebar_navigation(tmp_path, monkeypatch):
    app = load_app(tmp_path, monkeypatch)
    rendered = []

    class FailSidebar:
        def __getattr__(self, name):
            raise AssertionError(f"operator sidebar accessed via {name}")

    monkeypatch.setattr(
        app,
        "st",
        SimpleNamespace(
            query_params={"customer_response_token": "valid-token"},
            session_state={},
            sidebar=FailSidebar(),
        ),
    )
    monkeypatch.setattr(app, "customer_response_page", rendered.append)

    app.main()

    assert rendered == ["valid-token"]
