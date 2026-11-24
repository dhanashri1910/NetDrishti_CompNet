"""PDF generation for complete NetDrishti network topology and health reports."""
import json
import textwrap
from datetime import datetime

from engine.simulator import Sim
from engine.faults import CATALOG

W, H, M = 595, 842, 50


def _esc(value):
    value = str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return value.encode("latin-1", "replace").decode("latin-1")


def make_pdf(blocks, path, title="NetDrishti Network Report"):
    """Create a dependency-free text PDF from (style, text) blocks."""
    pages, current, y = [], [], H - M
    sizes = {
        "h1": (20, 26, "F2", 60),
        "h2": (13, 20, "F2", 85),
        "p": (10, 14, "F1", 95),
        "mono": (8.5, 11.5, "F3", 105),
        "sp": (0, 8, "F1", 1),
    }

    for style, text in blocks:
        size, leading, font, wrap_width = sizes[style]
        lines = [""] if style == "sp" else sum(
            (textwrap.wrap(line, wrap_width, break_long_words=True) or [""]
             for line in str(text).split("\n")),
            []
        )
        if style == "h2":
            y -= 6
        for line in lines:
            if y - leading < M:
                pages.append(current)
                current, y = [], H - M
            y -= leading
            if line:
                current.append(
                    f"BT /{font} {size} Tf {M} {y:.1f} Td ({_esc(line)}) Tj ET"
                )

    pages.append(current)
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
    ]
    kids = []
    for page_number, page in enumerate(pages, 1):
        page = page + [
            f"BT /F1 8 Tf {M} 28 Td ({_esc(title)} - page {page_number} of {len(pages)}) Tj ET"
        ]
        stream = "\n".join(page)
        objects.append(
            f"<< /Length {len(stream.encode('latin-1', 'replace'))} >>\nstream\n{stream}\nendstream"
        )
        content_id = len(objects)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        kids.append(f"{len(objects)} 0 R")

    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{index} 0 obj\n{obj}\nendobj\n".encode("latin-1", "replace")
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    with open(path, "wb") as pdf_file:
        pdf_file.write(output)
    return path


def _device_is_up(device):
    if device.get("up") is False:
        return False
    return all(interface.get("up", True) for interface in device.get("ifaces", []))


def network_report_blocks(net, user):
    """Build an all-in-one report from the selected network's saved topology."""
    from models import Fault

    topology = net.to_topology()
    devices = topology.get("devices", [])
    links = topology.get("links", [])
    simulator = Sim(topology)
    matrix = simulator.matrix()
    by_id = {device.get("id"): device for device in devices}
    type_counts = {}
    for device in devices:
        kind = device.get("type", "unknown")
        type_counts[kind] = type_counts.get(kind, 0) + 1

    up_devices = sum(1 for device in devices if _device_is_up(device))
    up_links = sum(1 for link in links if link.get("up", True))
    faults = Fault.query.filter_by(network_id=net.id).order_by(Fault.id).all()

    blocks = [
        ("h1", "NetDrishti - Complete Network Report"),
        ("p", "Intelligent Network Diagnosis, Monitoring and Troubleshooting Platform"),
        ("p", f"Network: {net.name}"),
        ("p", f"Prepared for: {user.full_name} ({user.email})"),
        ("p", f"Generated: {datetime.now():%Y-%m-%d %H:%M}"),
        ("sp", ""),
        ("h2", "1. Executive Summary"),
        ("p", f"Network description: {net.description or 'Not provided.'}"),
        ("p", f"Total devices: {len(devices)} | Operational devices: {up_devices} | "
              f"Total links: {len(links)} | Active links: {up_links}"),
        ("p", "Device categories: " + (", ".join(
            f"{kind}: {count}" for kind, count in sorted(type_counts.items())
        ) or "No devices configured.")),
        ("p", f"Simulated network health: {matrix.get('health', 0)}% "
              f"({matrix.get('ok', 0)} successful checks out of {matrix.get('total', 0)})."),
        ("p", "Important: connectivity, latency, throughput and health values in this report are generated by "
              "NetDrishti's internal simulator. They are not measurements from a live physical network."),
        ("sp", ""),
        ("h2", "2. Overall Topology and Connection Map"),
    ]

    if not devices:
        blocks.append(("p", "No devices are currently saved in this network."))
    else:
        blocks.append(("p", "Each line below represents a saved physical/logical connection in the topology. "
                            "The link cost is used by the routing experiment."))
        if not links:
            blocks.append(("p", "No links are configured."))
        for link in links:
            source = by_id.get(link.get("source"), {})
            target = by_id.get(link.get("target"), {})
            source_name = source.get("name", link.get("source", "Unknown"))
            target_name = target.get("name", link.get("target", "Unknown"))
            status = "UP" if link.get("up", True) else "DOWN"
            blocks.append(("mono", f"{source_name} [{link.get('source')}] -- "
                                   f"cost {link.get('cost', 1)} / {status} -- "
                                   f"{target_name} [{link.get('target')}]"))

    blocks.append(("h2", "3. Complete Device Inventory and Configuration"))
    if not devices:
        blocks.append(("p", "No device configuration is available."))
    for index, device in enumerate(devices, 1):
        name = device.get("name", device.get("id", "Unnamed device"))
        dtype = device.get("type", "unknown")
        status = "UP" if _device_is_up(device) else "DOWN"
        blocks.append(("p", f"{index}. {name} | ID: {device.get('id')} | Type: {dtype} | Status: {status}"))

        interfaces = device.get("ifaces", [])
        if interfaces:
            for interface in interfaces:
                ip = interface.get("ip") or "Not assigned"
                mask = interface.get("mask") or "Not assigned"
                vlan = interface.get("vlan")
                iface_status = "UP" if interface.get("up", True) else "DOWN"
                blocks.append(("mono", f"Interface {interface.get('name', 'unnamed')}: "
                                       f"IP {ip} | Mask {mask} | VLAN {vlan if vlan is not None else '-'} | {iface_status}"))
        else:
            blocks.append(("mono", "Interfaces: none configured"))

        if device.get("gateway"):
            blocks.append(("mono", f"Default gateway: {device.get('gateway')}"))
        if device.get("dns"):
            blocks.append(("mono", f"DNS server: {device.get('dns')}"))
        if device.get("vlans") is not None:
            blocks.append(("mono", f"Switch VLANs: {device.get('vlans')}"))
        if device.get("routes"):
            for route in device.get("routes", []):
                blocks.append(("mono", f"Route: {route.get('dest', '-')} via {route.get('via', '-')} "
                                       f"interface {route.get('iface', '-')}"))
        if device.get("services"):
            blocks.append(("mono", f"Services: {', '.join(map(str, device.get('services', [])))}"))
        if device.get("records"):
            for hostname, address in device.get("records", {}).items():
                blocks.append(("mono", f"DNS record: {hostname} -> {address}"))
        blocks.append(("sp", ""))

    blocks.append(("h2", "4. Link Inventory"))
    if not links:
        blocks.append(("p", "No network links are configured."))
    for index, link in enumerate(links, 1):
        source = by_id.get(link.get("source"), {})
        target = by_id.get(link.get("target"), {})
        blocks.append(("mono", f"{index}. {source.get('name', link.get('source'))} <-> "
                               f"{target.get('name', link.get('target'))} | "
                               f"Status: {'UP' if link.get('up', True) else 'DOWN'} | "
                               f"Cost: {link.get('cost', 1)} | Link ID: {link.get('id', '-')}"))

    blocks.append(("h2", "5. Connectivity and Network Health"))
    if not matrix.get("rows"):
        blocks.append(("p", "The simulator did not produce connectivity checks for this topology."))
    for row in matrix.get("rows", []):
        result = "REACHABLE" if row.get("ok") else "UNREACHABLE"
        latency = row.get("latency_ms")
        reason = row.get("reason") or ""
        blocks.append(("mono", f"{row.get('src_name')} -> {row.get('dst_name')}: {result} | "
                               f"Latency: {latency if latency is not None else '-'} ms | {reason}"))
    blocks.append(("p", f"Overall simulated health: {matrix.get('health', 0)}%. "
                         f"Successful checks: {matrix.get('ok', 0)}; failed checks: "
                         f"{matrix.get('total', 0) - matrix.get('ok', 0)}."))

    blocks.append(("h2", "6. Fault Detection and Diagnosis"))
    if not faults:
        blocks.append(("p", "No fault records have been saved for this network."))
    for fault in faults:
        fault_name = CATALOG.get(fault.code, {}).get("name", fault.code)
        blocks.append(("p", f"{fault.code} - {fault_name} | Severity: {fault.severity or '-'} | "
                             f"Device: {fault.device_name or '-'} | Status: {fault.status}"))
        if fault.description:
            blocks.append(("p", f"Description: {fault.description}"))
        if fault.diagnosis:
            diagnosis = fault.diagnosis
            blocks.append(("p", f"Root cause: {diagnosis.root_cause or '-'}\n"
                                 f"Explanation: {diagnosis.explanation or '-'}\n"
                                 f"Recommended solution: {diagnosis.solution or '-'}\n"
                                 f"Expected result: {diagnosis.expected_result or '-'}"))

    blocks.append(("h2", "7. Human-Approved Repair History"))
    repair_actions = [(fault, action) for fault in faults for action in fault.repairs]
    if not repair_actions:
        blocks.append(("p", "No repair decisions have been recorded."))
    for fault, action in repair_actions:
        decision = (action.decision or "unknown").upper()
        blocks.append(("p", f"{fault.code} on {fault.device_name or 'device'} | Decision: {decision} | "
                             f"Recovery verified: {'YES' if action.success else 'NO'}"))
        if action.applied_fix:
            blocks.append(("mono", f"Applied correction: {action.applied_fix}"))
        try:
            before = json.loads(action.before_json or "{}")
            after = json.loads(action.after_json or "{}")
            if before or after:
                blocks.append(("p", f"Before: {before.get('ok', '-')}/{before.get('total', '-')} "
                                     f"successful checks, health {before.get('health', '-')}%. "
                                     f"After: {after.get('ok', '-')}/{after.get('total', '-')} "
                                     f"successful checks, health {after.get('health', '-')}%."))
        except (TypeError, ValueError):
            blocks.append(("p", "Before/after connectivity details were not available."))

    blocks.extend([
        ("h2", "8. Conclusion"),
        ("p", f"The report summarizes {len(devices)} device(s) and {len(links)} link(s) in the saved "
              f"topology. The current simulated network health is {matrix.get('health', 0)}%. "
              f"{len(faults)} fault record(s) are available, including detection, diagnosis and repair "
              "history where recorded. Use the Topology Builder to update devices or connections, save "
              "the network, and generate a fresh report to reflect those changes."),
    ])
    return blocks
