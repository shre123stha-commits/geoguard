"""Phase 3 API tests: auth (3.1), parcels (3.2), errors/pagination (3.3), users (3.4).
Run against geoguard_test through the transactional `api` fixture; skipped without a DB."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import UserRole
from app.repositories import UserRepository
from app.services.throttle import LoginThrottle

ADMIN = ("admin@geoguard.test", "admin-password-1")
OFFICER = ("officer@geoguard.test", "officer-password-1")
SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[80.19, 12.935], [80.2, 12.935], [80.2, 12.945], [80.19, 12.945], [80.19, 12.935]]
    ],
}
BOWTIE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}


def _fc(*features: dict, **extra: object) -> dict:  # type: ignore[type-arg]
    return {"type": "FeatureCollection", "features": list(features), **extra}


def _feat(geometry: dict, **props: object) -> dict:  # type: ignore[type-arg]
    return {"type": "Feature", "geometry": geometry, "properties": props}


@pytest.fixture
def seeded(api: tuple[TestClient, Session]) -> tuple[TestClient, Session]:
    client, db = api
    repo = UserRepository(db)
    repo.create(ADMIN[0], "Admin", ADMIN[1], UserRole.admin)
    repo.create(OFFICER[0], "Officer", OFFICER[1], UserRole.officer)
    db.flush()
    return client, db


Login = Callable[[str, str], dict[str, str]]


@pytest.fixture
def login(seeded: tuple[TestClient, Session]) -> Login:
    client, _ = seeded

    def _login(email: str, password: str) -> dict[str, str]:
        r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login


# ---------- 3.1 auth ----------


def test_login_me_and_wrong_password(seeded: tuple[TestClient, Session]) -> None:
    client, _ = seeded
    r = client.post("/api/v1/auth/login", json={"email": ADMIN[0].upper(), "password": ADMIN[1]})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["user"]["role"] == "admin"
    hdr = {"Authorization": f"Bearer {body['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=hdr)
    assert me.status_code == 200 and me.json()["email"] == ADMIN[0]

    bad = client.post("/api/v1/auth/login", json={"email": ADMIN[0], "password": "nope-nope-1"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "unauthorized"
    unknown = client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "whatever1"})
    assert unknown.status_code == 401
    assert unknown.json()["error"]["message"] == bad.json()["error"]["message"]


def test_protected_routes_reject_missing_or_bad_token(seeded: tuple[TestClient, Session]) -> None:
    client, _ = seeded
    assert client.get("/api/v1/auth/me").status_code == 401
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_login_throttled_after_five_failures(seeded: tuple[TestClient, Session]) -> None:
    client, _ = seeded
    for _ in range(4):
        r = client.post("/api/v1/auth/login", json={"email": OFFICER[0], "password": "bad-bad-bad"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": OFFICER[0], "password": "bad-bad-bad"})
    assert r.status_code == 429 and "Retry-After" in r.headers
    # even the right password is refused during cooldown
    r = client.post("/api/v1/auth/login", json={"email": OFFICER[0], "password": OFFICER[1]})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_requests"
    # other accounts unaffected
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}
        ).status_code
        == 200
    )


def test_throttle_unit_cooldown_expires() -> None:
    t = LoginThrottle(max_failures=2, cooldown_s=10)
    assert t.record_failure("k", now=0.0) == 0
    assert t.record_failure("k", now=1.0) == 10
    assert t.retry_after("k", now=2.0) == 9
    assert t.retry_after("k", now=11.5) == 0


def test_must_change_password_blocks_everything_except_change(
    seeded: tuple[TestClient, Session],
) -> None:
    client, db = seeded
    UserRepository(db).create(
        "fresh@geoguard.test", "Fresh", "temporary-pass1", must_change_password=True
    )
    db.flush()
    r = client.post(
        "/api/v1/auth/login", json={"email": "fresh@geoguard.test", "password": "temporary-pass1"}
    )
    hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert r.json()["user"]["must_change_password"] is True
    assert client.get("/api/v1/parcels", headers=hdr).status_code == 403
    same = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "temporary-pass1", "new_password": "temporary-pass1"},
        headers=hdr,
    )
    assert same.status_code == 400
    wrong = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong-wrong-1", "new_password": "brand-new-pass-1"},
        headers=hdr,
    )
    assert wrong.status_code == 400
    short = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "temporary-pass1", "new_password": "short"},
        headers=hdr,
    )
    assert short.status_code == 422
    ok = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "temporary-pass1", "new_password": "brand-new-pass-1"},
        headers=hdr,
    )
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False
    assert client.get("/api/v1/parcels", headers=hdr).status_code == 200


def test_deactivated_user_token_stops_working(
    seeded: tuple[TestClient, Session], login: Login
) -> None:
    client, db = seeded
    off = login(*OFFICER)
    assert client.get("/api/v1/auth/me", headers=off).status_code == 200
    user = UserRepository(db).get_by_email(OFFICER[0])
    assert user is not None
    user.is_active = False
    db.flush()
    assert client.get("/api/v1/auth/me", headers=off).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": OFFICER[0], "password": OFFICER[1]})
    assert r.status_code == 401


# ---------- 3.2 parcels ----------


def test_parcels_crud_roles_and_area(seeded: tuple[TestClient, Session], login: Login) -> None:
    client, _ = seeded
    adm, off = login(*ADMIN), login(*OFFICER)

    body = _fc(
        _feat(SQUARE, name="Square", category="wetland"), source="upload", source_ref="a.geojson"
    )
    assert client.post("/api/v1/parcels", json=body, headers=off).status_code == 403
    r = client.post("/api/v1/parcels", json=body, headers=adm)
    assert r.status_code == 201, r.text
    created = r.json()["created"]
    assert len(created) == 1 and r.json()["skipped"] == []
    props = created[0]["properties"]
    pid = created[0]["id"]
    assert props["source"] == "upload" and props["source_ref"] == "a.geojson"
    # ~1.08 km x 1.1 km near the equator → geodesic area about 1.2 km²
    assert 1.15e6 < props["area_m2"] < 1.25e6
    assert created[0]["geometry"]["type"] == "MultiPolygon"

    lst = client.get("/api/v1/parcels", headers=off)
    assert lst.status_code == 200
    assert lst.json()["total"] == 1 and lst.json()["type"] == "FeatureCollection"
    assert client.get("/api/v1/parcels?category=forest", headers=off).json()["total"] == 0
    assert client.get("/api/v1/parcels?q=squ", headers=off).json()["total"] == 1

    one = client.get(f"/api/v1/parcels/{pid}", headers=off)
    assert one.status_code == 200 and one.json()["properties"]["name"] == "Square"
    assert client.get(f"/api/v1/parcels/{uuid.uuid4()}", headers=off).status_code == 404

    p = client.patch(f"/api/v1/parcels/{pid}", json={"name": "S2"}, headers=off)
    assert p.status_code == 403
    p = client.patch(f"/api/v1/parcels/{pid}", json={"name": "S2", "notes": "n"}, headers=adm)
    assert p.status_code == 200 and p.json()["properties"]["name"] == "S2"
    # uploaded parcels cannot be redrawn
    redraw = client.patch(f"/api/v1/parcels/{pid}", json={"geometry": SQUARE}, headers=adm)
    assert redraw.status_code == 409

    assert client.delete(f"/api/v1/parcels/{pid}", headers=off).status_code == 403
    d = client.delete(f"/api/v1/parcels/{pid}", headers=adm)
    assert d.status_code == 200 and d.json()["deleted"] == pid
    assert client.get(f"/api/v1/parcels/{pid}", headers=adm).status_code == 404


def test_parcels_invalid_features_are_skipped_with_reasons(
    seeded: tuple[TestClient, Session], login: Login
) -> None:
    client, _ = seeded
    adm = login(*ADMIN)
    out_of_range = {
        "type": "Polygon",
        "coordinates": [[[500, 0], [501, 0], [501, 1], [500, 1], [500, 0]]],
    }
    body = _fc(
        _feat(SQUARE, name="ok", category="wetland"),
        _feat(BOWTIE, name="bowtie", category="wetland"),
        _feat({"type": "Point", "coordinates": [80.19, 12.93]}, name="pt", category="x"),
        _feat(SQUARE, name="no-category"),
        _feat(out_of_range, name="range", category="x"),
        _feat({"type": "Polygon", "coordinates": "garbage"}, name="garbage", category="x"),
        category="default-cat",
    )
    r = client.post("/api/v1/parcels", json=body, headers=adm)
    assert r.status_code == 201, r.text
    res = r.json()
    # feature #4 gets the request-level default category, so it is created too
    assert [f["properties"]["name"] for f in res["created"]] == ["ok", "no-category"]
    reasons = {s["name"]: s["reason"] for s in res["skipped"]}
    assert "not valid" in reasons["bowtie"] and "Self-intersection" in reasons["bowtie"]
    assert "expected Polygon" in reasons["pt"]
    assert "EPSG:4326" in reasons["range"]
    assert "garbage" in reasons

    # all invalid → 422, nothing stored
    r = client.post("/api/v1/parcels", json=_fc(_feat(BOWTIE, name="b", category="c")), headers=adm)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert client.get("/api/v1/parcels", headers=adm).json()["total"] == 2


def test_drawn_parcel_default_name_and_redraw(
    seeded: tuple[TestClient, Session], login: Login
) -> None:
    client, _ = seeded
    adm = login(*ADMIN)
    r = client.post(
        "/api/v1/parcels",
        json=_fc(_feat(SQUARE), source="drawn", category="wetland"),
        headers=adm,
    )
    assert r.status_code == 201, r.text
    f = r.json()["created"][0]
    assert f["properties"]["name"] == "Parcel 1" and f["properties"]["source"] == "drawn"
    smaller = {
        "type": "Polygon",
        "coordinates": [
            [[80.19, 12.935], [80.195, 12.935], [80.195, 12.94], [80.19, 12.94], [80.19, 12.935]]
        ],
    }
    p = client.patch(f"/api/v1/parcels/{f['id']}", json={"geometry": smaller}, headers=adm)
    assert p.status_code == 200
    assert p.json()["properties"]["area_m2"] < f["properties"]["area_m2"] / 3
    bad = client.patch(f"/api/v1/parcels/{f['id']}", json={"geometry": BOWTIE}, headers=adm)
    assert bad.status_code == 422


def test_parcel_vertex_cap(seeded: tuple[TestClient, Session], login: Login) -> None:
    import math

    client, _ = seeded
    adm = login(*ADMIN)
    n = 6000
    ring = [
        [80.19 + 0.01 * math.cos(2 * math.pi * i / n), 12.94 + 0.01 * math.sin(2 * math.pi * i / n)]
        for i in range(n)
    ]
    ring.append(ring[0])
    poly = {"type": "Polygon", "coordinates": [ring]}
    r = client.post("/api/v1/parcels", json=_fc(_feat(poly, name="big", category="c")), headers=adm)
    assert r.status_code == 422 and "too many vertices" in r.json()["error"]["message"]


# ---------- 3.3 errors + pagination ----------


def test_validation_and_pagination_shape(seeded: tuple[TestClient, Session], login: Login) -> None:
    client, _ = seeded
    adm = login(*ADMIN)
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422
    assert set(r.json()["error"]) == {"code", "message", "details"}
    assert r.json()["error"]["code"] == "validation_error"

    for i in range(3):
        client.post(
            "/api/v1/parcels",
            json=_fc(_feat(SQUARE, name=f"P{i}", category="c")),
            headers=adm,
        )
    page = client.get("/api/v1/parcels?page=2&page_size=2", headers=adm).json()
    assert page["total"] == 3 and page["page"] == 2 and len(page["features"]) == 1
    assert client.get("/api/v1/parcels?page=0", headers=adm).status_code == 422
    assert client.get("/api/v1/parcels?page_size=999", headers=adm).status_code == 422


# ---------- 3.4 users ----------


def test_users_admin_only_crud(seeded: tuple[TestClient, Session], login: Login) -> None:
    client, _ = seeded
    adm, off = login(*ADMIN), login(*OFFICER)
    assert client.get("/api/v1/users", headers=off).status_code == 403

    lst = client.get("/api/v1/users", headers=adm).json()
    assert lst["total"] == 2 and {u["email"] for u in lst["items"]} == {ADMIN[0], OFFICER[0]}
    assert "password_hash" not in lst["items"][0]

    new = {"email": "New@Geoguard.test", "full_name": "New", "password": "temporary-pass1"}
    r = client.post("/api/v1/users", json=new, headers=adm)
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "new@geoguard.test"
    assert r.json()["role"] == "officer" and r.json()["must_change_password"] is True
    assert client.post("/api/v1/users", json=new, headers=adm).status_code == 409
    weak = {**new, "email": "w@geoguard.test", "password": "short"}
    assert client.post("/api/v1/users", json=weak, headers=adm).status_code == 422

    uid = r.json()["id"]
    p = client.patch(f"/api/v1/users/{uid}", json={"role": "admin", "full_name": "N2"}, headers=adm)
    assert p.status_code == 200 and p.json()["role"] == "admin" and p.json()["full_name"] == "N2"
    # password reset forces a change at next login
    p = client.patch(f"/api/v1/users/{uid}", json={"new_password": "reset-password-1"}, headers=adm)
    assert p.json()["must_change_password"] is True
    r = client.post(
        "/api/v1/auth/login", json={"email": "new@geoguard.test", "password": "reset-password-1"}
    )
    assert r.status_code == 200
    # deactivate
    p = client.patch(f"/api/v1/users/{uid}", json={"is_active": False}, headers=adm)
    assert p.json()["is_active"] is False
    assert client.get(f"/api/v1/users/{uuid.uuid4()}", headers=adm).status_code == 404


def test_last_admin_protection(seeded: tuple[TestClient, Session], login: Login) -> None:
    client, db = seeded
    adm = login(*ADMIN)
    me = client.get("/api/v1/auth/me", headers=adm).json()
    r = client.patch(f"/api/v1/users/{me['id']}", json={"role": "officer"}, headers=adm)
    assert r.status_code == 409 and "last active administrator" in r.json()["error"]["message"]
    r = client.patch(f"/api/v1/users/{me['id']}", json={"is_active": False}, headers=adm)
    assert r.status_code == 409
    # with a second admin, demotion of the first is allowed; self-deactivation still refused
    other = client.post(
        "/api/v1/users",
        json={
            "email": "a2@geoguard.test",
            "full_name": "A2",
            "password": "second-admin-1",
            "role": "admin",
        },
        headers=adm,
    ).json()

    def patch(uid: str, **body: object) -> int:
        return int(client.patch(f"/api/v1/users/{uid}", json=body, headers=adm).status_code)

    assert patch(other["id"], role="officer") == 200
    assert patch(other["id"], role="admin") == 200
    assert patch(me["id"], is_active=False) == 409
    assert patch(me["id"], role="officer") == 200
    # the demoted admin loses admin routes immediately
    assert client.get("/api/v1/users", headers=adm).status_code == 403
