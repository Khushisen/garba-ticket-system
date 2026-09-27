from tests.conftest import login


def test_login_page_loads(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_admin_login_succeeds(client, seed):
    resp = login(client, "admin", "adminpass123")
    assert resp.status_code == 200

    dashboard = client.get("/admin/")
    assert dashboard.status_code == 200


def test_scanner_login_succeeds_and_redirects_to_scanner(client, seed):
    resp = login(client, "scanner1", "scannerpass123")
    assert resp.status_code == 200
    assert b"GARBA ENTRY SCANNER" in resp.data or b"scanner" in resp.data.lower()


def test_wrong_password_rejected(client, seed):
    resp = login(client, "admin", "wrongpassword")
    assert b"Invalid username or password" in resp.data


def test_unauthorized_access_to_admin_redirects_to_login(client):
    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers["Location"]


def test_scanner_cannot_access_admin_only_routes(client, seed):
    login(client, "scanner1", "scannerpass123")
    resp = client.get("/admin/staff")
    assert resp.status_code == 403


def test_scanner_can_access_scanner_page(client, seed):
    login(client, "scanner1", "scannerpass123")
    resp = client.get("/admin/scanner")
    assert resp.status_code == 200
