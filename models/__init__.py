import json
from datetime import datetime
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created = db.Column(db.DateTime, default=datetime.utcnow)


class Network(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(300), default="")
    baseline_json = db.Column(db.Text, default="")
    created = db.Column(db.DateTime, default=datetime.utcnow)
    updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    devices = db.relationship("Device", backref="network", cascade="all, delete-orphan")
    links = db.relationship("Link", backref="network", cascade="all, delete-orphan")
    faults = db.relationship("Fault", backref="network", cascade="all, delete-orphan")

    def to_topology(self):
        return {"devices": [d.to_dict() for d in self.devices], "links": [l.to_dict() for l in self.links]}

    def save_topology(self, topo):
        for d in list(self.devices):
            db.session.delete(d)
        for l in list(self.links):
            db.session.delete(l)
        db.session.flush()
        for d in topo.get("devices", []):
            cfg = {k: v for k, v in d.items() if k not in ("id", "name", "type", "x", "y")}
            db.session.add(Device(network_id=self.id, key=d["id"], name=d.get("name", d["id"]),
                                  dtype=d["type"], x=float(d.get("x", 0)), y=float(d.get("y", 0)),
                                  config=json.dumps(cfg)))
        for l in topo.get("links", []):
            db.session.add(Link(network_id=self.id, key=l["id"], source=l["source"], target=l["target"],
                                up=bool(l.get("up", True)), cost=int(l.get("cost", 1))))
        self.updated = datetime.utcnow()


class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    network_id = db.Column(db.Integer, db.ForeignKey("network.id"), nullable=False, index=True)
    key = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    dtype = db.Column(db.String(20), nullable=False)  # pc | switch | router | server
    x = db.Column(db.Float, default=0)
    y = db.Column(db.Float, default=0)
    config = db.Column(db.Text, default="{}")

    def to_dict(self):
        d = {"id": self.key, "name": self.name, "type": self.dtype, "x": self.x, "y": self.y}
        d.update(json.loads(self.config or "{}"))
        return d


class Link(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    network_id = db.Column(db.Integer, db.ForeignKey("network.id"), nullable=False, index=True)
    key = db.Column(db.String(40), nullable=False)
    source = db.Column(db.String(40), nullable=False)
    target = db.Column(db.String(40), nullable=False)
    up = db.Column(db.Boolean, default=True)
    cost = db.Column(db.Integer, default=1)

    def to_dict(self):
        return {"id": self.key, "source": self.source, "target": self.target, "up": self.up, "cost": self.cost}


class Fault(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    network_id = db.Column(db.Integer, db.ForeignKey("network.id"), nullable=False, index=True)
    code = db.Column(db.String(8), nullable=False)
    fingerprint = db.Column(db.String(200), nullable=False)
    device_key = db.Column(db.String(40))
    device_name = db.Column(db.String(80))
    severity = db.Column(db.String(12))
    description = db.Column(db.Text)
    fix_json = db.Column(db.Text, default="{}")
    status = db.Column(db.String(20), default="detected")  # detected|repaired|rejected|repair_failed|cleared
    created = db.Column(db.DateTime, default=datetime.utcnow)
    diagnosis = db.relationship("Diagnosis", backref="fault", uselist=False, cascade="all, delete-orphan")
    repairs = db.relationship("RepairAction", backref="fault", cascade="all, delete-orphan")


class Diagnosis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fault_id = db.Column(db.Integer, db.ForeignKey("fault.id"), nullable=False)
    root_cause = db.Column(db.Text)
    explanation = db.Column(db.Text)
    solution = db.Column(db.Text)
    expected_result = db.Column(db.Text)
    ai_text = db.Column(db.Text, default="")


class RepairAction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fault_id = db.Column(db.Integer, db.ForeignKey("fault.id"), nullable=False)
    decision = db.Column(db.String(12))  # approve | reject
    applied_fix = db.Column(db.Text, default="{}")
    before_json = db.Column(db.Text, default="{}")
    after_json = db.Column(db.Text, default="{}")
    success = db.Column(db.Boolean, default=False)
    created = db.Column(db.DateTime, default=datetime.utcnow)



class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    network_id = db.Column(db.Integer, nullable=True)
    kind = db.Column(db.String(20), default="info")  # info|fault|repair|alert|ping
    message = db.Column(db.String(300))
    health = db.Column(db.Float, nullable=True)
    created = db.Column(db.DateTime, default=datetime.utcnow)
