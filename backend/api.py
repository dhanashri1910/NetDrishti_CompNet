
import copy
import json
import os
import math
from datetime import datetime

from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user

from models import (
    db, Network, Fault, Diagnosis, RepairAction, ActivityLog
)

from engine.simulator import Sim, validate_topology
from engine import faults as F, routing as R, subnet as S
from engine.sockets_demo import DEMOS
import reports


bp = Blueprint("api", __name__)


@bp.before_request
def _auth():
    if not current_user.is_authenticated:
        return jsonify(error="Authentication required."), 401


def err(msg, code=400):
    return jsonify(error=msg), code


def get_net(nid):
    n = db.session.get(Network, nid)
    if not n or n.user_id != current_user.id:
        return None
    return n


def log(kind, msg, net=None, health=None):
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            network_id=net.id if net else None,
            kind=kind,
            message=msg[:290],
            health=health
        )
    )


# ------------------------------------------------------------------
# NETWORKS
# ------------------------------------------------------------------

@bp.get("/networks")
def list_networks():
    return jsonify([
        {"id": n.id, "name": n.name, "devices": len(n.devices)}
        for n in Network.query.filter_by(
            user_id=current_user.id
        ).order_by(Network.id).all()
    ])


@bp.post("/networks")
def create_network():
    name = (request.json or {}).get("name", "").strip() or "Untitled network"

    n = Network(user_id=current_user.id, name=name[:120])
    db.session.add(n)
    db.session.commit()

    return jsonify(id=n.id, name=n.name)


@bp.post("/networks/sample")
def load_sample():
    path = os.path.join(
        current_app.config["DATA_FOLDER"],
        "sample_network.json"
    )

    data = json.load(open(path, encoding="utf-8"))

    n = Network.query.filter_by(
        user_id=current_user.id,
        name=data["name"]
    ).first()

    if not n:
        n = Network(
            user_id=current_user.id,
            name=data["name"],
            description=data["description"]
        )
        db.session.add(n)
        db.session.flush()

    n.save_topology(data["topology"])
    n.baseline_json = json.dumps(data["topology"])

    for f in list(n.faults):
        db.session.delete(f)

    log(
        "info",
        "Sample network loaded",
        n,
        Sim(data["topology"]).matrix()["health"]
    )

    db.session.commit()

    return jsonify(id=n.id)


@bp.get("/networks/<int:nid>")
def get_network(nid):
    n = get_net(nid)

    if not n:
        return err("Network not found.", 404)

    return jsonify(
        id=n.id,
        name=n.name,
        topology=n.to_topology()
    )


@bp.put("/networks/<int:nid>")
def save_network(nid):
    n = get_net(nid)

    if not n:
        return err("Network not found.", 404)

    body = request.json or {}
    topo = body.get("topology", {})

    errors = validate_topology(topo)

    if errors:
        return err(" ".join(errors[:4]))

    if body.get("name"):
        n.name = body["name"][:120]

    n.save_topology(topo)

    if body.get("set_baseline", True) and not n.baseline_json:
        n.baseline_json = json.dumps(topo)

    if body.get("set_baseline_now"):
        n.baseline_json = json.dumps(topo)

    db.session.commit()

    return jsonify(ok=True)


@bp.delete("/networks/<int:nid>")
def delete_network(nid):
    n = get_net(nid)

    if not n:
        return err("Network not found.", 404)

    db.session.delete(n)
    db.session.commit()

    return jsonify(ok=True)


@bp.post("/networks/<int:nid>/reset")
def reset_network(nid):
    n = get_net(nid)

    if not n or not n.baseline_json:
        return err("No saved baseline to restore. Save a healthy topology first.")

    n.save_topology(json.loads(n.baseline_json))

    for f in n.faults:
        if f.status == "detected":
            f.status = "cleared"

    log("info", "Network restored to healthy baseline", n)

    db.session.commit()

    return jsonify(ok=True)


@bp.post("/networks/<int:nid>/baseline")
def set_baseline(nid):
    n = get_net(nid)

    if not n:
        return err("Network not found.", 404)

    n.baseline_json = json.dumps(n.to_topology())

    db.session.commit()

    return jsonify(ok=True)


# ------------------------------------------------------------------
# SIMULATION
# ------------------------------------------------------------------

@bp.post("/networks/<int:nid>/ping")
def ping(nid):
    n = get_net(nid)

    if not n:
        return err("Network not found.", 404)

    b = request.json or {}
    topo = n.to_topology()

    if b.get("src") not in {d["id"] for d in topo["devices"]}:
        return err("Choose a source device.")

    if not str(b.get("target", "")).strip():
        return err("Enter a target IP address or hostname.")

    r = Sim(topo).ping(b["src"], b["target"])

    log(
        "ping",
        f"Ping {r['src_name']} → {b['target']}: {'OK' if r['ok'] else 'FAILED'}",
        n
    )

    db.session.commit()

    return jsonify(r)


@bp.get("/networks/<int:nid>/matrix")
def matrix(nid):
    n = get_net(nid)

    if not n:
        return err("Network not found.", 404)

    return jsonify(Sim(n.to_topology()).matrix())


# ------------------------------------------------------------------
# FAULTS
# ------------------------------------------------------------------

@bp.post("/networks/<int:nid>/faults/inject")
def inject(nid):
    n = get_net(nid)

    if not n:
        return err("Network not found.", 404)

    b = request.json or {}
    topo = n.to_topology()

    try:
        desc = F.inject(
            topo,
            b.get("code"),
            b.get("device"),
            b.get("link"),
            b.get("value")
        )

    except (ValueError, KeyError, StopIteration) as e:
        return err(
            str(e) or "Cannot inject this fault on the selected target."
        )

    n.save_topology(topo)

    h = Sim(topo).matrix()["health"]

    log(
        "fault",
        f"Injected {b.get('code')}: {desc}",
        n,
        h
    )

    db.session.commit()

    return jsonify(
        ok=True,
        description=desc,
        health=h
    )


def _sync_faults(n, topo, use_ai=False):
    found = F.detect(topo)

    existing = {
        f.fingerprint: f
        for f in n.faults
        if f.status in ("detected", "repair_failed", "rejected")
    }

    keys = set()

    for d in found:
        keys.add(d["fingerprint"])

        row = existing.get(d["fingerprint"])

        if not row:
            row = Fault(
                network_id=n.id,
                code=d["code"],
                fingerprint=d["fingerprint"],
                device_key=d["device_id"],
                device_name=d["device_name"],
                severity=d["severity"],
                description=d["description"],
                fix_json=json.dumps(d["fix"]),
                status="detected"
            )

            db.session.add(row)
            db.session.flush()

            dg = F.diagnose(
                d,
                use_ai,
                current_app.config["ANTHROPIC_API_KEY"],
                current_app.config["AI_MODEL"]
            )

            db.session.add(
                Diagnosis(fault_id=row.id, **dg)
            )

            log(
                "alert",
                f"Detected {d['code']} {d['name']} on {d['device_name']}",
                n
            )

        else:
            row.fix_json = json.dumps(d["fix"])
            row.description = d["description"]

    for fp, row in existing.items():
        if fp not in keys:
            row.status = "cleared"

    db.session.flush()

    out = []

    for d in found:
        row = Fault.query.filter_by(
            network_id=n.id,
            fingerprint=d["fingerprint"]
        ).order_by(Fault.id.desc()).first()

        dg = row.diagnosis

        out.append({
            **d,
            "id": row.id,
            "status": row.status,
            "diagnosis": {
                "root_cause": dg.root_cause,
                "explanation": dg.explanation,
                "solution": dg.solution,
                "expected_result": dg.expected_result,
                "ai_text": dg.ai_text
            }
        })

    return out


@bp.get("/networks/<int:nid>/faults/detect")
def detect(nid):
    n = get_net(nid)

    if not n:
        return err("Network not found.", 404)

    topo = n.to_topology()

    found = _sync_faults(
        n,
        topo,
        request.args.get("ai") == "1"
    )

    h = Sim(topo).matrix()["health"]

    log(
        "info",
        f"Fault scan: {len(found)} issue(s) detected",
        n,
        h
    )

    db.session.commit()

    return jsonify(
        faults=found,
        health=h
    )


@bp.post("/faults/<int:fid>/decision")
def decision(fid):
    f = db.session.get(Fault, fid)

    n = get_net(f.network_id) if f else None

    if not n:
        return err("Fault not found.", 404)

    b = request.json or {}

    if b.get("decision") == "reject":
        f.status = "rejected"

        db.session.add(
            RepairAction(
                fault_id=f.id,
                decision="reject"
            )
        )

        log(
            "repair",
            f"Repair of {f.code} on {f.device_name} rejected by operator",
            n
        )

        db.session.commit()

        return jsonify(status="rejected")

    if b.get("decision") != "approve":
        return err("Decision must be 'approve' or 'reject'.")

    topo = n.to_topology()

    fault = {
        "fix": json.loads(f.fix_json),
        "fingerprint": f.fingerprint
    }

    try:
        new, res = F.heal(
            topo,
            fault,
            b.get("value")
        )

    except (ValueError, KeyError, StopIteration, TypeError) as e:
        return err(f"Repair could not be applied: {e}")

    n.save_topology(new)

    f.status = "repaired" if res["resolved"] else "repair_failed"

    fix = fault["fix"]

    if b.get("value"):
        fix["value"] = b["value"]

    db.session.add(
        RepairAction(
            fault_id=f.id,
            decision="approve",
            applied_fix=json.dumps(fix),
            before_json=json.dumps(res["before"]),
            after_json=json.dumps(res["after"]),
            success=res["resolved"]
        )
    )

    log(
        "repair",
        f"{res['action']} → {'recovered' if res['resolved'] else 'NOT resolved'}",
        n,
        res["after"]["health"]
    )

    db.session.commit()

    return jsonify(
        status=f.status,
        **res
    )


# ------------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------------

@bp.get("/dashboard")
def dashboard():
    nid = request.args.get("network", type=int)

    n = get_net(nid) if nid else None

    if not n:
        return jsonify(empty=True)

    topo = n.to_topology()
    st = Sim(topo).stats()

    open_f = [
        f for f in n.faults
        if f.status in ("detected", "repair_failed", "rejected")
    ]

    rec = [
        f for f in n.faults
        if f.status == "repaired"
    ]

    hist = ActivityLog.query.filter(
        ActivityLog.user_id == current_user.id,
        ActivityLog.network_id == n.id,
        ActivityLog.health.isnot(None)
    ).order_by(
        ActivityLog.id.desc()
    ).limit(20).all()[::-1]

    feed = ActivityLog.query.filter_by(
        user_id=current_user.id,
        network_id=n.id
    ).order_by(
        ActivityLog.id.desc()
    ).limit(10).all()

    return jsonify(
        empty=False,
        name=n.name,
        description=n.description,
        device_types={
            dtype: sum(1 for device in topo["devices"] if device.get("type") == dtype)
            for dtype in sorted({device.get("type", "unknown") for device in topo["devices"]})
        },
        health=st["health"],
        devices=st["devices"],
        active_devices=st["active_devices"],
        failed_devices=st["failed_devices"],
        active_links=st["active_links"],
        links=st["links"],
        detected=len(n.faults),
        open_faults=len(open_f),
        recovered=len(rec),

        history=[
            {
                "t": h.created.strftime("%H:%M:%S"),
                "health": h.health
            }
            for h in hist
        ],

        latency=[
            {
                "pair": f"{r['src_name']}→{r['dst_name']}",
                "ms": r["latency_ms"],
                "ok": r["ok"],
                "mbps": r["throughput_mbps"]
            }
            for r in st["matrix"]["rows"]
        ],

        loss=round(
            100 * (st["matrix"]["total"] - st["matrix"]["ok"])
            / max(1, st["matrix"]["total"]),
            1
        ),

        feed=[
            {
                "kind": a.kind,
                "msg": a.message,
                "t": a.created.strftime("%H:%M:%S")
            }
            for a in feed
        ],

        alerts=[
            {
                "code": f.code,
                "device": f.device_name,
                "severity": f.severity,
                "desc": f.description,
                "status": f.status
            }
            for f in open_f[:6]
        ]
    )


# ------------------------------------------------------------------
# ROUTING / TOOLS
# ------------------------------------------------------------------

@bp.get("/routing/graph")
def routing_graph():
    """Get devices and connections from the selected topology."""

    nid = request.args.get("network", type=int)
    source = request.args.get("source", "net")

    if source == "demo":
        return jsonify(
            nodes=[
                {"id": x, "label": x}
                for x in R.DEMO["nodes"]
            ],
            edges=R.DEMO["edges"]
        )

    if not nid:
        return err("Please select a network first.")

    n = get_net(nid)

    if not n:
        return err("Network not found.", 404)

    topo = n.to_topology()

    return jsonify(
        nodes=[
            {"id": d["id"], "label": d["name"]}
            for d in topo["devices"]
        ],
        edges=[
            {
                "a": link["source"],
                "b": link["target"],
                "cost": link.get("cost", 1),
                "up": link.get("up", True)
            }
            for link in topo["links"]
        ]
    )


@bp.put("/routing/costs")
def routing_update_costs():
    """Manually update costs of existing topology connections."""

    body = request.json or {}

    nid = body.get("network")
    updates = body.get("costs", [])

    if not nid:
        return err("Select a network first.")

    if not isinstance(updates, list) or not updates:
        return err("Provide at least one connection cost.")

    try:
        nid = int(nid)
    except (ValueError, TypeError):
        return err("Invalid network ID.")

    n = get_net(nid)

    if not n:
        return err("Network not found.", 404)

    topo = n.to_topology()
    links = topo.get("links", [])

    validated = []

    # Validate all costs before changing the topology.
    for item in updates:
        if not isinstance(item, dict):
            return err("Invalid connection data.")

        a = item.get("a")
        b = item.get("b")

        if not a or not b or a == b:
            return err("Invalid connection selected.")

        try:
            cost = float(item.get("cost"))
        except (TypeError, ValueError):
            return err("Connection cost must be a number.")

        if not math.isfinite(cost) or cost < 0:
            return err("Cost must be finite and non-negative.")

        link = next(
            (
                link for link in links
                if (
                    link.get("source") == a
                    and link.get("target") == b
                ) or (
                    link.get("source") == b
                    and link.get("target") == a
                )
            ),
            None
        )

        if link is None:
            return err(f"Connection {a} - {b} does not exist.")

        validated.append((link, cost))

    # Apply changes only after validation.
    for link, cost in validated:
        link["cost"] = cost

    n.save_topology(topo)

    log(
        "info",
        f"Updated routing costs for {len(validated)} connections",
        n
    )

    db.session.commit()

    return jsonify(
        ok=True,
        message="Connection costs updated successfully.",
        edges=[
            {
                "a": link["source"],
                "b": link["target"],
                "cost": link.get("cost", 1),
                "up": link.get("up", True)
            }
            for link in topo["links"]
        ]
    )


@bp.post("/routing/compute")
def routing_compute():
    """Calculate all available paths and find the cheapest route."""

    body = request.json or {}

    try:
        if body.get("source") == "demo":
            nodes = R.DEMO["nodes"]
            edges = R.DEMO["edges"]

        else:
            nid = body.get("network")

            if not nid:
                return err("Select a network first.")

            n = get_net(int(nid))

            if not n:
                return err("Network not found.", 404)

            topo = n.to_topology()

            nodes = [
                d["id"]
                for d in topo["devices"]
            ]

            edges = [
                {
                    "a": link["source"],
                    "b": link["target"],
                    "cost": link.get("cost", 1),
                    "up": link.get("up", True)
                }
                for link in topo["links"]
            ]

        src = body.get("src")
        dst = body.get("dst")

        if src not in nodes or dst not in nodes or src == dst:
            return err("Choose two different valid devices.")

        fail = body.get("fail", [])

        if not isinstance(fail, list):
            return err("Invalid failed connection list.")

        result = R.compute(
            nodes,
            edges,
            src,
            dst,
            fail
        )

        return jsonify(
            nodes=nodes,
            edges=edges,
            result=result
        )

    except (ValueError, KeyError, TypeError) as e:
        return err(f"Invalid routing request: {e}")


# ------------------------------------------------------------------
# SUBNET
# ------------------------------------------------------------------

@bp.post("/subnet")
def subnet():
    b = request.json or {}

    try:
        return jsonify(
            S.calc(
                b.get("ip", "").strip(),
                (b.get("mask") or "").strip() or None,
                b.get("prefix")
            )
        )

    except ValueError as e:
        return err(str(e))


# ------------------------------------------------------------------
# SOCKETS
# ------------------------------------------------------------------

@bp.post("/sockets/<proto>/<action>")
def sockets(proto, action):
    d = DEMOS.get(proto)

    if not d or action not in ("start", "send", "stop", "status"):
        return err("Unknown socket action.", 404)

    b = request.json or {}

    if action == "start":
        r = d.start(b.get("port"))

    elif action == "send":
        msg = str(b.get("message", "")).strip()

        if not msg:
            return err("Enter a message to send.")

        r = d.send(msg[:500])

    elif action == "stop":
        r = d.stop()

    else:
        r = {}

    return jsonify({
        **r,
        **d.status()
    })


# ------------------------------------------------------------------
# SCENARIOS
# ------------------------------------------------------------------

@bp.get("/scenarios")
def scenarios():
    return jsonify(
        json.load(
            open(
                os.path.join(
                    current_app.config["DATA_FOLDER"],
                    "fault_scenarios.json"
                ),
                encoding="utf-8"
            )
        )
    )


# ------------------------------------------------------------------
# CATALOG
# ------------------------------------------------------------------

@bp.get("/catalog")
def catalog():
    return jsonify({
        k: {
            "name": v["name"],
            "severity": v["severity"]
        }
        for k, v in F.CATALOG.items()
    })


# ------------------------------------------------------------------
# COMPLETE NETWORK TOPOLOGY REPORT
# ------------------------------------------------------------------

@bp.get("/report/network/<int:nid>")
def network_report(nid):
    """Generate a PDF containing the selected network's complete saved topology."""
    n = get_net(nid)
    if not n:
        return err("Network not found.", 404)

    blocks = reports.network_report_blocks(n, current_user)
    filename = f"NetDrishti_Network_Report_{n.id}.pdf"
    path = os.path.join(current_app.config["REPORT_FOLDER"], filename)
    reports.make_pdf(blocks, path, title="NetDrishti Network Report")

    log("info", "Complete network topology report generated", n)
    db.session.commit()

    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )
