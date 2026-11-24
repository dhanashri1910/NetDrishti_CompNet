import copy, json
import pytest
from engine import subnet, routing
from engine.simulator import Sim, validate_topology
from engine.faults import inject, detect, heal, diagnose, apply_fix


def codes(t): return [d["code"] for d in detect(t)]
def dev(t, i): return next(d for d in t["devices"] if d["id"] == i)


# ---------- auth ----------
def test_register_login_logout(client):
    r = client.post("/register", data={"full_name": "Ann Lee", "email": "ann@x.com", "password": "secret123", "confirm_password": "secret123"})
    assert r.status_code == 302
    assert client.post("/register", data={"full_name": "Ann", "email": "ann@x.com", "password": "secret123", "confirm_password": "secret123"}).status_code == 400  # duplicate
    assert client.post("/register", data={"full_name": "Bob", "email": "b@x.com", "password": "secret123", "confirm_password": "nope"}).status_code == 400
    assert client.get("/dashboard").status_code == 302  # protected
    assert client.post("/login", data={"email": "ann@x.com", "password": "bad"}).status_code == 401
    assert client.post("/login", data={"email": "ann@x.com", "password": "secret123"}).status_code == 302
    assert client.get("/dashboard").status_code == 200
    client.get("/logout"); assert client.get("/dashboard").status_code == 302


def test_password_is_hashed(app):
    from models import User
    with app.app_context():
        u = User.query.filter_by(email="admin@netpulse.lab").first()
        assert u.password_hash != "Admin@12345" and u.password_hash.startswith(("scrypt", "pbkdf2"))


def test_api_requires_login(client):
    assert client.get("/api/networks").status_code == 401


# ---------- subnet / IP validation ----------
def test_subnet_calculator():
    r = subnet.calc("192.168.1.77", prefix=26)
    assert (r["network"], r["broadcast"], r["first_usable"], r["last_usable"], r["total_addresses"], r["usable_hosts"]) == ("192.168.1.64", "192.168.1.127", "192.168.1.65", "192.168.1.126", 64, 62)
    assert subnet.calc("10.0.0.5", mask="255.255.255.252")["usable_hosts"] == 2
    assert subnet.calc("10.0.0.5", prefix=31)["usable_hosts"] == 2


@pytest.mark.parametrize("ip,ok", [("192.168.1.1", True), ("256.1.1.1", False), ("1.2.3", False), ("abc", False), ("", False)])
def test_ip_validation(ip, ok): assert subnet.valid_ip(ip) is ok


def test_mask_validation():
    assert subnet.valid_mask("255.255.255.0") and not subnet.valid_mask("255.0.255.0")
    with pytest.raises(ValueError): subnet.calc("1.1.1.1", mask="255.0.255.0")
    with pytest.raises(ValueError): subnet.calc("1.1.1.300", prefix=24)


def test_topology_validation(base):
    assert validate_topology(base) == []
    base["devices"][0]["ifaces"][0]["ip"] = "999.1.1.1"
    assert validate_topology(base)
    base["links"].append({"id": "x", "source": "pc1", "target": "pc1"})
    assert any("itself" in e for e in validate_topology(base))


# ---------- baseline connectivity ----------
def test_baseline_healthy(base):
    s = Sim(base); m = s.matrix()
    assert m["health"] == 100.0 and detect(base) == []
    p = s.ping("pc1", "192.168.20.10")
    assert p["ok"] and p["path"] == ["pc1", "sw1", "r1", "sw2", "pc3"] and p["simulated"]
    assert s.ping("pc1", "server.netdrishti.lab")["resolved_ip"] == "192.168.20.100"


# ---------- fault scenarios ----------
def test_gateway_validation(base):
    inject(base, "F02", "pc1")
    r = Sim(base).ping("pc1", "192.168.20.10")
    assert not r["ok"] and r["code"] == "F02" and "F02" in codes(base)
    assert Sim(base).ping("pc1", "192.168.10.11")["ok"]  # same subnet still works


def test_incorrect_ip(base):
    inject(base, "F01", "pc1"); assert codes(base) == ["F01"] and not Sim(base).ping("pc1", "192.168.10.11")["ok"]


def test_duplicate_ip(base):
    inject(base, "F05", "pc4")
    assert codes(base) == ["F05"]
    r = Sim(base).ping("pc1", "192.168.20.10"); assert not r["ok"] and r["code"] == "F05"


def test_interface_failure(base):
    inject(base, "F03", "pc3"); assert codes(base) == ["F03"]
    assert not Sim(base).ping("pc1", "192.168.20.10")["ok"]


def test_link_failure(base):
    inject(base, "F04", "srv1"); assert codes(base) == ["F04"]
    assert not Sim(base).ping("pc3", "192.168.20.100")["ok"] and Sim(base).ping("pc3", "192.168.20.11")["ok"]


def test_vlan_mismatch(base):
    inject(base, "F06", "pc2"); assert codes(base) == ["F06"]
    assert not Sim(base).ping("pc1", "192.168.10.11")["ok"]


def test_missing_route(base):
    inject(base, "F07", "r1"); assert codes(base) == ["F07"]
    assert not Sim(base).ping("pc1", "192.168.20.10")["ok"]


def test_dns_fault(base):
    inject(base, "F08", "pc1"); assert codes(base) == ["F08"]
    r = Sim(base).ping("pc1", "server.netdrishti.lab"); assert not r["ok"] and r["code"] == "F08"
    assert Sim(base).ping("pc1", "192.168.20.100")["ok"]


def test_inject_rejects_bad_target(base):
    with pytest.raises(ValueError): inject(base, "F07", "pc1")
    with pytest.raises(ValueError): inject(base, "F99", "pc1")


# ---------- diagnosis + recovery ----------
@pytest.mark.parametrize("code,target", [("F01", "pc1"), ("F02", "pc2"), ("F03", "pc3"), ("F04", "srv1"), ("F05", "pc4"), ("F06", "pc2"), ("F07", "r1"), ("F08", "pc1")])
def test_diagnosis_and_recovery(base, code, target):
    inject(base, code, target)
    f = detect(base)[0]; assert f["code"] == code
    d = diagnose(f)
    assert all(d[k] for k in ("root_cause", "explanation", "solution", "expected_result"))
    new, res = heal(base, f)
    assert res["resolved"] and res["after"]["health"] == 100.0 and res["after"]["health"] > res["before"]["health"] - 0.01
    assert detect(new) == []


def test_edit_correction(base):
    inject(base, "F08", "pc1"); f = detect(base)[0]
    new, _ = heal(base, f, "192.168.20.100"); assert dev(new, "pc1")["dns"] == "192.168.20.100"
    with pytest.raises(ValueError): apply_fix(copy.deepcopy(base), {"op": "set_dns", "device": "pc1"}, "bad")


def test_multi_fault(base):
    inject(base, "F03", "pc3"); inject(base, "F06", "pc2")
    assert set(codes(base)) == {"F03", "F06"}


# ---------- routing ----------
def test_routing_algorithms_agree_and_recalculate():
    r = routing.compute(routing.DEMO["nodes"], routing.DEMO["edges"], "A", "F", ["B-D"])
    b = r["before"]; assert b["agree"] and b["dijkstra"]["route"]["cost"] == b["bellman-ford"]["route"]["cost"] == 8
    assert b["dijkstra"]["route"]["path"] == ["A", "B", "C", "D", "F"]
    a = r["after"]; assert a["agree"] and a["dijkstra"]["route"]["cost"] == 8
    r2 = routing.compute(routing.DEMO["nodes"], routing.DEMO["edges"], "A", "F", ["C-D", "D-E", "D-F"])
    assert r2["after"]["dijkstra"]["route"]["path"][-1] == "F" and r2["after"]["dijkstra"]["route"]["cost"] > 8


def test_unreachable_destination():
    r = routing.compute(["A", "B", "C"], [{"a": "A", "b": "B", "cost": 1}], "A", "C", [])
    assert r["before"]["dijkstra"]["route"]["cost"] is None and r["before"]["bellman-ford"]["route"]["cost"] is None


def test_alternatives():
    g = routing.build_graph(routing.DEMO["nodes"], routing.DEMO["edges"])
    alts = routing.alternatives(g, "A", "F"); assert alts and alts[0]["cost"] >= 8


# ---------- sockets ----------
def test_tcp_udp_localhost():
    from engine.sockets_demo import Demo
    for proto in ("TCP", "UDP"):
        d = Demo(proto, 0); assert d.start(0)["ok"]
        try:
            r = d.send("ping"); assert r["ok"] and r["reply"].startswith(f"ACK({proto})")
        finally: d.stop()
        assert not d.send("x")["ok"]


# ---------- API end-to-end ----------
def test_end_to_end_api(admin):
    c = admin
    nid = c.post("/api/networks/sample", json={}).get_json()["id"]
    assert len(c.get(f"/api/networks/{nid}").get_json()["topology"]["devices"]) == 8
    # topology creation + link creation through the API
    topo = c.get(f"/api/networks/{nid}").get_json()["topology"]
    topo["devices"].append({"id": "pcx", "name": "PCX", "type": "pc", "x": 5, "y": 5, "up": True, "gateway": "", "dns": "", "ifaces": [{"name": "eth0", "ip": "192.168.10.50", "mask": "255.255.255.0", "vlan": 10, "up": True}]})
    topo["links"].append({"id": "lx", "source": "pcx", "target": "sw1", "up": True, "cost": 1})
    assert c.put(f"/api/networks/{nid}", json={"topology": topo}).status_code == 200
    assert any(l["id"] == "lx" for l in c.get(f"/api/networks/{nid}").get_json()["topology"]["links"])
    topo["links"].append({"id": "ly", "source": "pcx", "target": "sw1"})
    assert c.put(f"/api/networks/{nid}", json={"topology": topo}).status_code == 400  # duplicate link rejected
    # fault -> detect -> approve -> recovery
    c.post(f"/api/networks/{nid}/faults/reset", json={})
    c.post(f"/api/networks/{nid}/reset", json={})
    assert c.post(f"/api/networks/{nid}/faults/inject", json={"code": "F02", "device": "pc2"}).status_code == 200
    d = c.get(f"/api/networks/{nid}/faults/detect").get_json(); assert d["faults"][0]["code"] == "F02" and d["faults"][0]["diagnosis"]["root_cause"]
    r = c.post(f"/api/faults/{d['faults'][0]['id']}/decision", json={"decision": "approve"}).get_json()
    assert r["status"] == "repaired" and r["after"]["health"] == 100.0
    # reject path
    c.post(f"/api/networks/{nid}/faults/inject", json={"code": "F03", "device": "pc3"})
    d = c.get(f"/api/networks/{nid}/faults/detect").get_json()
    assert c.post(f"/api/faults/{d['faults'][0]['id']}/decision", json={"decision": "reject"}).get_json()["status"] == "rejected"
    dash = c.get(f"/api/dashboard?network={nid}").get_json(); assert dash["recovered"] == 1 and dash["detected"] == 2
    # PDF report
    r = c.get(f"/api/report/network/{nid}")
    assert r.status_code == 200 and r.data.startswith(b"%PDF") and r.data.rstrip().endswith(b"%%EOF")
    assert b"NetDrishti" in r.data and b"PC1" in r.data


def test_networks_are_user_specific(app):
    a, b = app.test_client(), app.test_client()
    a.post("/login", data={"email": "admin@netpulse.lab", "password": "Admin@12345"})
    nid = a.post("/api/networks/sample", json={}).get_json()["id"]
    b.post("/register", data={"full_name": "Zed", "email": "z@x.com", "password": "password1", "confirm_password": "password1"})
    b.post("/login", data={"email": "z@x.com", "password": "password1"})
    assert b.get(f"/api/networks/{nid}").status_code == 404 and b.get("/api/networks").get_json() == []


def test_pages_render(admin):
    admin.post("/api/networks/sample", json={})
    for p in ("dashboard", "topology", "faults", "routing", "tools", "reports"):
        assert admin.get("/" + p).status_code == 200, p
    assert admin.get("/packet-tracer").status_code == 404
    assert admin.get("/api/pt/status").status_code == 404
    assert admin.get("/api/experiments").status_code == 404
    assert admin.post("/api/subnet", json={"ip": "1.1.1.1"}).status_code == 400
