"""Internal network simulation engine. Everything here is SIMULATED - no real packets are sent.

Topology dict:
 devices: [{id,name,type(pc|switch|router|server),x,y,up,ifaces:[{name,ip,mask,vlan,up}],
            gateway,dns,vlans(switch),routes(router:[{dest,via:'connected'|ip,iface}]),services,records}]
 links:   [{id,source,target,up,cost}]
"""
import hashlib
import ipaddress
from engine.subnet import valid_ip, valid_mask

ENDPOINTS = ("pc", "server")


def iface_net(i):
    try:
        return ipaddress.IPv4Interface(f"{i.get('ip')}/{i.get('mask')}").network
    except ValueError:
        return None


def fail(code, reason, path=None):
    return {"ok": False, "code": code, "reason": reason, "path": path or []}


class Sim:
    def __init__(self, topo):
        self.devices = topo["devices"]
        self.links = topo["links"]
        self.dev = {d["id"]: d for d in self.devices}
        self.adj = {}
        for l in self.links:
            if l["source"] in self.dev and l["target"] in self.dev:
                self.adj.setdefault(l["source"], []).append((l["target"], l))
                self.adj.setdefault(l["target"], []).append((l["source"], l))

    # ---- helpers -------------------------------------------------------
    def name(self, did):
        return self.dev[did]["name"]

    def active_ifaces(self, d):
        if d.get("up", True) is False:
            return []
        return [i for i in d.get("ifaces", []) if i.get("up", True) and valid_ip(i.get("ip", ""))]

    def by_ip(self, ip):
        return [(d, i) for d in self.devices for i in d.get("ifaces", []) if i.get("ip") == ip]

    def l2(self, start, vlan):
        """Layer-2 flood domain for a VLAN: returns {node: parent}. Switches only forward allowed VLANs."""
        seen, q = {start: None}, [start]
        while q:
            n = q.pop(0)
            for m, l in self.adj.get(n, []):
                if m in seen or l.get("up", True) is False:
                    continue
                d = self.dev[m]
                if d["type"] == "switch":
                    if d.get("up", True) is not False and vlan in d.get("vlans", []):
                        seen[m] = n; q.append(m)
                elif any(i.get("vlan") == vlan for i in self.active_ifaces(d)):
                    seen[m] = n
        return seen

    @staticmethod
    def chain(seen, node):
        p = []
        while node is not None:
            p.append(node); node = seen[node]
        return p[::-1]

    # ---- forwarding ----------------------------------------------------
    def forward(self, src, dst_ip):
        d = self.dev[src]
        if d["type"] not in ENDPOINTS:
            return fail("SRC", "Source must be a PC or server.")
        if d.get("up", True) is False or not d.get("ifaces"):
            return fail("F03", f"{d['name']} is powered off or has no interface.")
        ifc = d["ifaces"][0]
        if ifc.get("up", True) is False:
            return fail("F03", f"Interface {ifc['name']} on {d['name']} is administratively down.")
        if not (valid_ip(ifc.get("ip", "")) and valid_mask(ifc.get("mask", ""))):
            return fail("F01", f"{d['name']} has an invalid IP address or mask.")
        if len(self.by_ip(ifc["ip"])) > 1:
            return fail("F05", f"Duplicate IP {ifc['ip']}: ARP conflict, delivery is unreliable.")
        net = iface_net(ifc)
        dst = ipaddress.IPv4Address(dst_ip)
        if dst in net:
            return self._l2_deliver(src, ifc, dst_ip, [])
        gw = d.get("gateway", "")
        if not valid_ip(gw):
            return fail("F02", f"{d['name']} has no valid default gateway for off-subnet destination {dst_ip}.")
        if ipaddress.IPv4Address(gw) not in net:
            return fail("F02", f"Default gateway {gw} is outside {d['name']}'s subnet {net}.")
        seen = self.l2(src, ifc.get("vlan"))
        owners = [(o, i) for o, i in self.by_ip(gw) if o["type"] == "router"]
        if not owners:
            return fail("F02", f"Gateway {gw} does not belong to any router (ARP for gateway gets no reply).")
        r = owners[0][0]
        if r["id"] not in seen:
            return fail("L2", f"Gateway {gw} is not reachable at Layer 2 from {d['name']} (VLAN {ifc.get('vlan')}, link, or interface problem).")
        return self.route(r["id"], dst_ip, self.chain(seen, r["id"]))

    def _l2_deliver(self, src, ifc, dst_ip, prefix):
        owners = self.by_ip(dst_ip)
        if len(owners) > 1:
            return fail("F05", f"Duplicate IP {dst_ip}: more than one device answers ARP.")
        seen = self.l2(src, ifc.get("vlan"))
        for o, i in owners:
            if o["id"] in seen and o["id"] != src:
                return {"ok": True, "path": prefix + self.chain(seen, o["id"]) if not prefix else prefix + self.chain(seen, o["id"])[1:], "target": o["id"]}
        return fail("L2", f"ARP for {dst_ip} unanswered: destination not in the same VLAN/broadcast domain or unreachable.")

    def route(self, r, dst_ip, path, ttl=8):
        R, ip = self.dev[r], ipaddress.IPv4Address(dst_ip)
        if ttl == 0:
            return fail("LOOP", "TTL expired - routing loop.", path)
        if R.get("up", True) is False:
            return fail("F03", f"Router {R['name']} is powered off.", path)
        best = None
        for rt in R.get("routes", []):
            try:
                n = ipaddress.ip_network(rt["dest"], strict=False)
            except ValueError:
                continue
            if ip in n and (best is None or n.prefixlen > best[0].prefixlen):
                best = (n, rt)
        if not best:
            return fail("F07", f"Router {R['name']} has no route to {dst_ip} (destination network unreachable).", path)
        rt = best[1]
        if rt.get("via") == "connected":
            ifc = next((i for i in R["ifaces"] if i["name"] == rt.get("iface")), None)
            if not ifc or ifc.get("up", True) is False:
                return fail("F03", f"Egress interface {rt.get('iface')} on {R['name']} is down.", path)
            seen = self.l2(r, ifc.get("vlan"))
            owners = self.by_ip(dst_ip)
            if len(owners) > 1:
                return fail("F05", f"Duplicate IP {dst_ip} on the destination network.", path)
            for o, i in owners:
                if o["id"] in seen:
                    return {"ok": True, "path": path + self.chain(seen, o["id"])[1:], "target": o["id"]}
            return fail("L2", f"{R['name']} cannot reach {dst_ip} on {rt.get('iface')} (ARP failed: VLAN/link/interface problem or wrong IP).", path)
        nh = rt["via"]
        for ifc in self.active_ifaces(R):
            n = iface_net(ifc)
            if n and valid_ip(nh) and ipaddress.IPv4Address(nh) in n:
                seen = self.l2(r, ifc.get("vlan"))
                for o, i in self.by_ip(nh):
                    if o["type"] == "router" and o["id"] in seen:
                        return self.route(o["id"], dst_ip, path + self.chain(seen, o["id"])[1:], ttl - 1)
        return fail("F07", f"Next hop {nh} for {rt['dest']} on {R['name']} is unreachable.", path)

    # ---- ping / DNS ----------------------------------------------------
    def resolve(self, src, name):
        d = self.dev[src]
        dns_ip = d.get("dns", "")
        servers = [o for o, i in self.by_ip(dns_ip) if "dns" in o.get("services", []) and o.get("up", True) is not False] if dns_ip else []
        if not servers:
            return None, f"DNS lookup failed: DNS server '{dns_ip or 'not set'}' does not exist or is not a DNS server (F08)."
        f = self.forward(src, dns_ip)
        if not f["ok"]:
            return None, f"DNS server {dns_ip} unreachable: {f['reason']}"
        rec = servers[0].get("records", {}).get(name.lower())
        return (rec, None) if rec else (None, f"DNS: name '{name}' not found (NXDOMAIN).")

    def ping(self, src, target):
        t = str(target).strip()
        res = {"src": src, "src_name": self.name(src), "target": t, "simulated": True}
        ip = t
        if not valid_ip(t):
            ip, err = self.resolve(src, t)
            if err:
                return {**res, "ok": False, "code": "F08", "reason": err, "path": [], "hops": 0, "latency_ms": None, "loss_pct": 100, "throughput_mbps": 0}
        res["resolved_ip"] = ip
        f = self.forward(src, ip)
        if not f["ok"]:
            return {**res, "ok": False, "code": f["code"], "reason": f["reason"], "path": f["path"], "hops": 0, "latency_ms": None, "loss_pct": 100, "throughput_mbps": 0}
        dst = f["target"]
        sip = self.dev[src]["ifaces"][0]["ip"]
        b = self.forward(dst, sip)
        if not b["ok"]:
            return {**res, "ok": False, "code": b["code"], "reason": f"Request delivered but reply failed: {b['reason']}", "path": f["path"], "hops": 0, "latency_ms": None, "loss_pct": 100, "throughput_mbps": 0}
        hops = len(f["path"]) - 1
        jitter = int(hashlib.md5((src + dst).encode()).hexdigest()[:2], 16) / 255 * 1.5
        return {**res, "ok": True, "code": "OK", "reason": "Reply received (simulated).", "path": f["path"], "reverse_path": b["path"],
                "target_id": dst, "hops": hops, "latency_ms": round(0.8 + hops * 1.7 + jitter, 2), "loss_pct": 0,
                "throughput_mbps": round(94.0 / max(1, hops) ** 0.5, 1)}

    def matrix(self):
        eps = [d for d in self.devices if d["type"] in ENDPOINTS and d.get("ifaces")]
        rows = []
        for i, a in enumerate(eps):
            for b in eps[i + 1:]:
                ip = b["ifaces"][0].get("ip", "")
                r = self.ping(a["id"], ip) if valid_ip(ip) else {"ok": False, "reason": "Target has no valid IP", "code": "F01", "path": [], "latency_ms": None, "hops": 0}
                rows.append({"src": a["id"], "dst": b["id"], "src_name": a["name"], "dst_name": b["name"], "ok": r["ok"],
                             "reason": r["reason"], "code": r["code"], "latency_ms": r["latency_ms"], "hops": r["hops"], "path": r["path"],
                             "throughput_mbps": r.get("throughput_mbps", 0)})
        recs = next((x.get("records", {}) for x in self.devices if "dns" in x.get("services", []) and x.get("records")), {})
        if recs:
            for a in eps:
                if a.get("dns") and "dns" not in a.get("services", []):
                    mine = a["ifaces"][0].get("ip")
                    live = {i.get("ip") for x in self.devices for i in x.get("ifaces", [])}
                    name0 = next((k for k in sorted(recs) if recs[k] != mine and recs[k] in live), next((k for k in sorted(recs) if recs[k] != mine), sorted(recs)[0]))
                    r = self.ping(a["id"], name0)
                    rows.append({"src": a["id"], "dst": "dns", "src_name": a["name"], "dst_name": f"DNS: {name0}", "ok": r["ok"], "reason": r["reason"],
                                 "code": r["code"], "latency_ms": r["latency_ms"], "hops": r["hops"], "path": r["path"], "throughput_mbps": r.get("throughput_mbps", 0)})
        ok = sum(1 for r in rows if r["ok"])
        return {"rows": rows, "total": len(rows), "ok": ok, "health": round(100 * ok / len(rows), 1) if rows else 100.0}

    def stats(self):
        m = self.matrix()
        down = [d for d in self.devices if d.get("up", True) is False or any(i.get("up", True) is False for i in d.get("ifaces", []))]
        up_links = [l for l in self.links if l.get("up", True)]
        return {"devices": len(self.devices), "failed_devices": len(down), "active_devices": len(self.devices) - len(down),
                "links": len(self.links), "active_links": len(up_links), "failed_links": len(self.links) - len(up_links),
                "health": m["health"], "pairs_ok": m["ok"], "pairs_total": m["total"], "matrix": m}


def validate_topology(topo):
    """Return list of error strings for a topology payload."""
    errs, ids = [], set()
    for d in topo.get("devices", []):
        if d.get("type") not in ("pc", "switch", "router", "server"):
            errs.append(f"Unknown device type for {d.get('id')}.")
        if d.get("id") in ids:
            errs.append(f"Duplicate device id {d.get('id')}.")
        ids.add(d.get("id"))
        for i in d.get("ifaces", []):
            if i.get("ip") and not valid_ip(i["ip"]):
                errs.append(f"{d.get('name')}: invalid IP '{i['ip']}'.")
            if i.get("mask") and not valid_mask(i["mask"]):
                errs.append(f"{d.get('name')}: invalid subnet mask '{i['mask']}'.")
        if d.get("gateway") and not valid_ip(d["gateway"]):
            errs.append(f"{d.get('name')}: invalid gateway '{d['gateway']}'.")
    pairs = set()
    for l in topo.get("links", []):
        if l["source"] not in ids or l["target"] not in ids:
            errs.append(f"Link {l.get('id')} references a missing device.")
        if l["source"] == l["target"]:
            errs.append("A device cannot be linked to itself.")
        k = frozenset((l["source"], l["target"]))
        if k in pairs:
            errs.append(f"Duplicate link between {l['source']} and {l['target']}.")
        pairs.add(k)
    return errs
