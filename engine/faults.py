"""Rule-based fault injection, detection, diagnosis and repair (simulator only)."""
import copy
import ipaddress
import json
import os
import urllib.request
from collections import Counter
from engine.simulator import Sim, iface_net, ENDPOINTS
from engine.subnet import valid_ip, valid_mask

CATALOG = {
    "F01": dict(name="Incorrect IP address", severity="high",
        cause="Host IP address lies outside the subnet used by its VLAN/gateway, or is malformed.",
        explanation="The host's address does not belong to the network of the other devices in its broadcast domain, so ARP and the same-subnet check fail and traffic is sent to the wrong place.",
        solution="Assign an unused address from the correct subnet (keep the mask and gateway).",
        expected="Host can reach peers in its subnet and the default gateway again."),
    "F02": dict(name="Incorrect default gateway", severity="high",
        cause="Default gateway is empty, outside the host subnet, or not the router interface address.",
        explanation="Local traffic works but packets for other subnets are sent to a gateway that does not exist or is not a router, so inter-subnet communication fails.",
        solution="Set the default gateway to the router interface IP in the host's subnet.",
        expected="Inter-subnet pings through the router succeed."),
    "F03": dict(name="Disabled network interface", severity="critical",
        cause="Interface (or device) is administratively shut down.",
        explanation="A shutdown interface does not send or receive frames, so every path through it is lost.",
        solution="Enable the interface ('no shutdown') or power the device on.",
        expected="Link layer comes up and connectivity through the device is restored."),
    "F04": dict(name="Broken network link", severity="critical",
        cause="Physical cable/link between two devices is down.",
        explanation="With no layer-1 connectivity, frames cannot cross the link; devices behind it become isolated unless a redundant path exists.",
        solution="Replace/reseat the cable or re-enable the link.",
        expected="Devices behind the link are reachable again."),
    "F05": dict(name="Duplicate IP address", severity="high",
        cause="Two devices are configured with the same IP address.",
        explanation="Both devices answer ARP for the same address, so traffic alternates or fails and sessions are unreliable.",
        solution="Give one of the devices a unique unused IP address from the subnet.",
        expected="ARP resolves to a single device and communication is stable."),
    "F06": dict(name="VLAN mismatch", severity="high",
        cause="Port VLAN does not match the VLANs permitted on the attached switch.",
        explanation="The switch does not forward the host's VLAN, so the host is isolated in its own broadcast domain.",
        solution="Move the host/interface to a VLAN that the switch carries (the intended VLAN).",
        expected="Host rejoins its VLAN and reaches its gateway and peers."),
    "F07": dict(name="Missing routing entry", severity="high",
        cause="Router lacks a route (connected or static) for an active network.",
        explanation="Without a matching route the router drops packets for that destination ('network unreachable').",
        solution="Add the missing route (connected network or static route) to the routing table.",
        expected="Router forwards packets to the destination network again."),
    "F08": dict(name="DNS misconfiguration", severity="medium",
        cause="Host points at a DNS server address that is not a DNS server.",
        explanation="IP connectivity works but names cannot be resolved, so users cannot reach services by hostname.",
        solution="Set the DNS server to the address of the network's DNS server.",
        expected="Hostnames resolve and ping by name succeeds."),
}


def _ifc(d, idx=0):
    return d["ifaces"][min(idx, len(d["ifaces"]) - 1)]


def struct_peers(sim, did):
    """Endpoints attached through switches, ignoring link state and VLANs; also returns VLANs carried."""
    seen, q, out, vlans = {did}, [did], [], set()
    while q:
        n = q.pop(0)
        for m, _ in sim.adj.get(n, []):
            if m in seen:
                continue
            seen.add(m)
            if sim.dev[m]["type"] == "switch":
                q.append(m); vlans.update(sim.dev[m].get("vlans", []))
            else:
                out.append(m)
    return out, vlans


def expected_net(sim, did):
    peers, vlans = struct_peers(sim, did)
    votes = Counter()
    me = sim.dev[did]
    for p in peers:
        P = sim.dev[p]
        for i in P.get("ifaces", []):
            n = iface_net(i)
            if not n:
                continue
            if P["type"] == "router":
                if (vlans and i.get("vlan") in vlans) or (not vlans and i.get("vlan") == _ifc(me).get("vlan")):
                    votes[n] += 2
            else:
                votes[n] += 1
    return votes.most_common(1)[0][0] if votes else None


def free_ip(sim, net, prefer=None):
    used = {i.get("ip") for d in sim.devices for i in d.get("ifaces", [])}
    base, size = int(net.network_address), net.num_addresses
    if prefer and str(prefer).split(".")[-1].isdigit():
        off = int(str(prefer).split(".")[-1])  # keep the host part when possible
        cand = ipaddress.IPv4Address(base + off) if 0 < off < size - 1 else None
        if cand and str(cand) not in used:
            return str(cand)
    for off in list(range(50, min(size - 1, 254))) + list(range(2, min(size - 1, 50))) + [1]:
        if 0 < off < size - 1:
            c = str(ipaddress.IPv4Address(base + off))
            if c not in used:
                return c
    return ""


def detect(topo):
    sim, out = Sim(topo), []
    names = {d["id"]: d["name"] for d in topo["devices"]}

    def add(code, did, desc, fix, link=None, iface=None):
        c = CATALOG[code]
        out.append({"code": code, "name": c["name"], "severity": c["severity"], "device_id": did, "device_name": names.get(did, did),
                    "description": desc, "probable_cause": c["cause"], "recommendation": c["solution"], "fix": fix,
                    "fingerprint": f"{code}|{did}|{link or ''}|{iface or ''}"})

    # F05 duplicates
    owners = {}
    for d in sim.devices:
        for i in d.get("ifaces", []):
            if valid_ip(i.get("ip", "")):
                owners.setdefault(i["ip"], []).append((d, i))
    for ip, lst in owners.items():
        if len({d["id"] for d, _ in lst}) > 1:
            d, i = lst[-1]
            net = iface_net(i) or expected_net(sim, d["id"])
            add("F05", d["id"], f"IP {ip} is configured on {', '.join(x['name'] for x, _ in lst)}.",
                {"op": "set_ip", "device": d["id"], "iface": i["name"], "value": free_ip(sim, net) if net else ""}, iface=i["name"])
    dup_devs = {d["id"] for ip, lst in owners.items() if len({x['id'] for x, _ in lst}) > 1 for d, _ in lst}

    for d in sim.devices:
        did, t = d["id"], d["type"]
        # F03
        if d.get("up", True) is False:
            add("F03", did, f"{d['name']} is powered off / administratively down.", {"op": "set_device_up", "device": did})
        for i in d.get("ifaces", []):
            if i.get("up", True) is False:
                add("F03", did, f"Interface {i['name']} on {d['name']} is shut down.", {"op": "set_iface_up", "device": did, "iface": i["name"]}, iface=i["name"])
        # F06
        adj_sw = [sim.dev[m] for m, _ in sim.adj.get(did, []) if sim.dev[m]["type"] == "switch"]
        if adj_sw:
            allowed = set().union(*[set(s.get("vlans", [])) for s in adj_sw])
            for i in d.get("ifaces", []):
                if i.get("vlan") not in allowed and t != "switch":
                    good = sorted(allowed)[0] if allowed else 1
                    add("F06", did, f"{d['name']} {i['name']} is in VLAN {i.get('vlan')} but the attached switch carries VLAN(s) {sorted(allowed)}.",
                        {"op": "set_vlan", "device": did, "iface": i["name"], "value": good}, iface=i["name"])
        if t in ENDPOINTS and d.get("ifaces"):
            i = d["ifaces"][0]
            en = expected_net(sim, did)
            bad_ip = not (valid_ip(i.get("ip", "")) and valid_mask(i.get("mask", "")))
            wrong = (not bad_ip) and en is not None and ipaddress.IPv4Address(i["ip"]) not in en
            if bad_ip or wrong:
                add("F01", did, f"{d['name']} IP {i.get('ip') or '(none)'}/{i.get('mask') or '?'} is not in the expected subnet {en or '?'}.",
                    {"op": "set_ip", "device": did, "iface": i["name"], "value": free_ip(sim, en, i.get("ip")) if en else ""}, iface=i["name"])
            elif did not in dup_devs or True:
                # F02 only when own IP is sane
                routers_here = []
                if en:
                    peers, _ = struct_peers(sim, did)
                    routers_here = [(sim.dev[p], x) for p in peers if sim.dev[p]["type"] == "router" for x in sim.dev[p]["ifaces"] if iface_net(x) == en]
                gw, net = d.get("gateway", ""), iface_net(i)
                if routers_here:
                    good = routers_here[0][1]["ip"]
                    if not valid_ip(gw) or ipaddress.IPv4Address(gw) not in net or gw not in [x["ip"] for _, x in routers_here]:
                        add("F02", did, f"{d['name']} default gateway is '{gw or 'not set'}'; the router interface in this subnet is {good}.",
                            {"op": "set_gateway", "device": did, "value": good})
            # F08
            dns = d.get("dns", "")
            dns_srv = [s for s in sim.devices if "dns" in s.get("services", [])]
            if dns and not any(ifc.get("ip") == dns for s in dns_srv for ifc in s.get("ifaces", [])):
                good = dns_srv[0]["ifaces"][0]["ip"] if dns_srv else ""
                add("F08", did, f"{d['name']} uses DNS server {dns}, which is not a DNS server in this network.",
                    {"op": "set_dns", "device": did, "value": good})
        # F07
        if t == "router":
            have = {(r.get("iface")) for r in d.get("routes", []) if r.get("via") == "connected"}
            for i in sim.active_ifaces(d):
                if i["name"] not in have and iface_net(i):
                    add("F07", did, f"{d['name']} has no connected route for {iface_net(i)} ({i['name']}).",
                        {"op": "add_route", "device": did, "iface": i["name"], "value": str(iface_net(i))}, iface=i["name"])
    for l in topo["links"]:
        if l.get("up", True) is False:
            add("F04", l["source"], f"Link {names.get(l['source'])} ↔ {names.get(l['target'])} is down.",
                {"op": "set_link_up", "link": l["id"]}, link=l["id"])
    return out


def apply_fix(topo, fix, override=None):
    """Apply a repair to the in-memory topology. Returns description."""
    f = dict(fix)
    if override not in (None, ""):
        f["value"] = override
    op = f["op"]
    dev = next((d for d in topo["devices"] if d["id"] == f.get("device")), None)
    ifc = next((i for i in (dev or {}).get("ifaces", []) if i["name"] == f.get("iface")), None)
    if op == "set_ip":
        if not valid_ip(f.get("value", "")):
            raise ValueError("Repair value must be a valid IPv4 address.")
        ifc["ip"] = f["value"]; return f"Set {dev['name']} {ifc['name']} IP to {f['value']}"
    if op == "set_gateway":
        if not valid_ip(f.get("value", "")):
            raise ValueError("Repair value must be a valid IPv4 address.")
        dev["gateway"] = f["value"]; return f"Set {dev['name']} gateway to {f['value']}"
    if op == "set_dns":
        if not valid_ip(f.get("value", "")):
            raise ValueError("Repair value must be a valid IPv4 address.")
        dev["dns"] = f["value"]; return f"Set {dev['name']} DNS to {f['value']}"
    if op == "set_iface_up":
        ifc["up"] = True; return f"Enabled {ifc['name']} on {dev['name']}"
    if op == "set_device_up":
        dev["up"] = True; return f"Powered on {dev['name']}"
    if op == "set_link_up":
        lk = next(l for l in topo["links"] if l["id"] == f["link"]); lk["up"] = True; return f"Restored link {lk['source']}–{lk['target']}"
    if op == "set_vlan":
        ifc["vlan"] = int(f["value"]); return f"Set {dev['name']} {ifc['name']} to VLAN {f['value']}"
    if op == "add_route":
        dev.setdefault("routes", []).append({"dest": f["value"], "via": "connected", "iface": f["iface"]}); return f"Added connected route {f['value']} on {dev['name']}"
    raise ValueError("Unknown repair operation")


def inject(topo, code, device_id, link_id=None, value=None):
    """Inject one of F01..F08 into the topology (in place). Returns a description."""
    dev = next((d for d in topo["devices"] if d["id"] == device_id), None)
    if code not in CATALOG:
        raise ValueError("Unknown fault code.")
    if not dev and code != "F04":
        raise ValueError("Select a target device.")
    t = dev["type"] if dev else ""
    need = {"F01": ENDPOINTS, "F02": ENDPOINTS, "F05": ENDPOINTS, "F08": ENDPOINTS, "F07": ("router",), "F06": ENDPOINTS + ("router",)}
    if code in need and t not in need[code]:
        raise ValueError(f"{code} ({CATALOG[code]['name']}) needs a target of type: {', '.join(need[code])}.")
    if code == "F01":
        i = _ifc(dev); last = i["ip"].split(".")[-1]
        i["ip"] = value or f"10.99.99.{last}"; return f"{dev['name']} IP changed to {i['ip']}"
    if code == "F02":
        i = _ifc(dev); net = iface_net(i)
        dev["gateway"] = value or str(net.broadcast_address - 1); return f"{dev['name']} gateway changed to {dev['gateway']}"
    if code == "F03":
        if t == "switch":
            dev["up"] = False; return f"{dev['name']} switched off"
        i = _ifc(dev); i["up"] = False; return f"{dev['name']} {i['name']} shut down"
    if code == "F04":
        cand = [l for l in topo["links"] if (link_id and l["id"] == link_id) or (not link_id and device_id in (l["source"], l["target"]) and l.get("up", True))]
        if not cand:
            raise ValueError("No link found for this device.")
        cand[0]["up"] = False; return f"Link {cand[0]['source']}–{cand[0]['target']} cut"
    if code == "F05":
        i = _ifc(dev); net = iface_net(i)
        peers = [d for d in topo["devices"] if d["id"] != dev["id"] and d["type"] in ENDPOINTS and d.get("ifaces") and iface_net(d["ifaces"][0]) == net]
        if not peers:
            raise ValueError("No peer in the same subnet to duplicate.")
        i["ip"] = peers[0]["ifaces"][0]["ip"]; return f"{dev['name']} now uses {i['ip']} (same as {peers[0]['name']})"
    if code == "F06":
        i = _ifc(dev); i["vlan"] = int(value or 99); return f"{dev['name']} {i['name']} moved to VLAN {i['vlan']}"
    if code == "F07":
        r = next((r for r in dev.get("routes", []) if r.get("via") == "connected"), None)
        if not r:
            raise ValueError("Router has no connected route to remove.")
        dev["routes"].remove(r); return f"Removed route {r['dest']} from {dev['name']}"
    if code == "F08":
        dev["dns"] = value or "192.168.99.53"; return f"{dev['name']} DNS changed to {dev['dns']}"


def diagnose(fault, use_ai=False, api_key="", model=""):
    c = CATALOG[fault["code"]]
    d = {"root_cause": f"{c['cause']} Observed: {fault['description']}", "explanation": c["explanation"],
         "solution": f"{c['solution']} Proposed change: {json.dumps(fault['fix'])}", "expected_result": c["expected"], "ai_text": ""}
    if use_ai and api_key:
        d["ai_text"] = ai_explain(fault, api_key, model)
    return d


def ai_explain(fault, api_key, model):
    """Optional AI explanation. Core app works without it; failures are swallowed."""
    try:
        body = json.dumps({"model": model, "max_tokens": 300, "messages": [{"role": "user", "content":
            f"Explain briefly (max 120 words) for a networking student: fault {fault['code']} {fault['name']} on {fault['device_name']}: {fault['description']}"}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["content"][0]["text"]
    except Exception as e:  # noqa
        return f"(AI explanation unavailable: {type(e).__name__})"


def heal(topo, fault, override=None):
    """Simulated repair + recovery verification. Returns (new_topo, summary dict)."""
    before = Sim(topo).matrix()
    new = copy.deepcopy(topo)
    desc = apply_fix(new, fault["fix"], override)
    after = Sim(new).matrix()
    still = [f for f in detect(new) if f["fingerprint"] == fault["fingerprint"]]
    return new, {"action": desc, "before": before, "after": after, "resolved": not still,
                 "improved": after["ok"] >= before["ok"]}
