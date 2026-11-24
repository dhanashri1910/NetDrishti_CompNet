/* NetDrishti core helpers: API wrapper, toasts, network selection, Cytoscape styling */
const NP = {
  net: null,
  async api(url, opts = {}) {
    const o = Object.assign({ headers: {} }, opts);
    if (o.json !== undefined) { o.method = o.method || 'POST'; o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(o.json); }
    const r = await fetch(url, o);
    let d = {}; try { d = await r.json(); } catch (e) {}
    if (!r.ok) { const m = d.error || ('Request failed (' + r.status + ')'); NP.toast(m, 'danger'); throw new Error(m); }
    return d;
  },
  toast(msg, kind = 'info') {
    const el = document.createElement('div');
    el.className = `toast align-items-center text-bg-${kind === 'danger' ? 'danger' : kind === 'success' ? 'success' : 'dark'} border-0`;
    el.innerHTML = `<div class="d-flex"><div class="toast-body"></div><button class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
    el.querySelector('.toast-body').textContent = msg;
    document.getElementById('toasts').appendChild(el);
    new bootstrap.Toast(el, { delay: 4000 }).show();
  },
  esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); },
  async loadNetworks(selectId = null) {
    const sel = document.getElementById('netSelect');
    const list = await NP.api('/api/networks');
    sel.innerHTML = list.map(n => `<option value="${n.id}">${NP.esc(n.name)}</option>`).join('') || '<option value="">No networks yet</option>';
    let id = selectId || localStorage.getItem('np_net');
    if (!list.find(n => String(n.id) === String(id))) id = list.length ? list[0].id : null;
    sel.value = id || ''; NP.net = id ? Number(id) : null; localStorage.setItem('np_net', id || '');
    return list;
  },
  async ensureNetwork() { // used by pages: returns network id or null
    const list = await NP.loadNetworks();
    document.getElementById('netSelect').onchange = e => { localStorage.setItem('np_net', e.target.value); location.reload(); };
    return NP.net;
  },
  async loadSample() {
    const r = await NP.api('/api/networks/sample', { json: {} });
    localStorage.setItem('np_net', r.id); NP.toast('Sample network loaded', 'success'); location.reload();
  },
  emptyState(el) {
    el.innerHTML = `<div class="card-np text-center py-5"><i class="fa-solid fa-diagram-project fa-2x mb-3 text-secondary"></i>
      <p class="mb-3">No network yet. Load the ready-made sample topology to start.</p>
      <button class="btn btn-np" onclick="NP.loadSample()">Load sample network</button></div>`;
  },
  cyStyle: [
    { selector: 'node', style: { 'label': 'data(label)', 'color': '#dbe5ff', 'font-size': 11, 'text-valign': 'bottom', 'text-margin-y': 6,
      'width': 46, 'height': 46, 'background-color': '#16213d', 'border-width': 3, 'border-color': '#22c55e', 'text-wrap': 'wrap', 'text-max-width': 110,
      'background-fit': 'contain', 'background-image': 'data(icon)', 'background-width': '60%', 'background-height': '60%' } },
    { selector: 'node[type="switch"]', style: { 'shape': 'round-rectangle' } },
    { selector: 'node[type="router"]', style: { 'shape': 'diamond', 'width': 54, 'height': 54 } },
    { selector: 'node[type="server"]', style: { 'shape': 'round-rectangle', 'width': 48, 'height': 52 } },
    { selector: 'node[status="down"]', style: { 'border-color': '#ef4444' } },
    { selector: 'node[status="fault"]', style: { 'border-color': '#f59e0b' } },
    { selector: 'node:selected', style: { 'overlay-color': '#22d3ee', 'overlay-opacity': .18, 'overlay-padding': 8 } },
    { selector: 'node.src', style: { 'border-color': '#3b82f6' } },
    { selector: 'edge', style: { 'width': 2.5, 'line-color': '#3b5bdb', 'curve-style': 'bezier', 'opacity': .9 } },
    { selector: 'edge[?down]', style: { 'line-color': '#ef4444', 'line-style': 'dashed' } },
    { selector: 'edge:selected', style: { 'line-color': '#22d3ee', 'width': 4 } },
    { selector: 'edge.path', style: { 'line-color': '#22d3ee', 'width': 4 } },
    { selector: 'node.path', style: { 'border-color': '#22d3ee' } },
    { selector: '.pkt', style: { 'width': 12, 'height': 12, 'shape': 'ellipse', 'background-color': '#f59e0b', 'border-width': 2, 'border-color': '#fff', 'label': '', 'background-image': 'none', 'z-index': 99 } },
  ],
  svgIcon(type) {
    const p = { pc: 'M4 5h16v10H4zM9 19h6M12 15v4', switch: 'M3 8h18v8H3zM7 12h.01M11 12h.01M15 12h.01', router: 'M12 3v6M12 15v6M3 12h6M15 12h6M9 9l-2-2M15 15l2 2', server: 'M5 4h14v6H5zM5 14h14v6H5zM8 7h.01M8 17h.01' }[type] || '';
    const s = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#22d3ee" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${p}"/></svg>`;
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(s);
  },
  deviceStatus(d) {
    if (d.up === false) return 'down';
    if ((d.ifaces || []).some(i => i.up === false)) return 'down';
    return 'up';
  },
  toElements(topo, faultsByDev = {}) {
    const nodes = topo.devices.map(d => ({ group: 'nodes', data: { id: d.id, label: d.name + (d.ifaces && d.ifaces[0] && d.ifaces[0].ip ? '\n' + d.ifaces[0].ip : ''), type: d.type, icon: NP.svgIcon(d.type),
      status: faultsByDev[d.id] ? 'fault' : NP.deviceStatus(d) }, position: { x: d.x, y: d.y } }));
    const edges = topo.links.map(l => ({ group: 'edges', data: { id: l.id, source: l.source, target: l.target, down: l.up === false } }));
    return nodes.concat(edges);
  },
  makeCy(container, topo, opts = {}) {
    return cytoscape(Object.assign({ container, elements: NP.toElements(topo, opts.faults || {}), style: NP.cyStyle, layout: { name: 'preset' }, wheelSensitivity: .3, minZoom: .4, maxZoom: 2.5 }, opts.cy || {}));
  },
  async animatePath(cy, path, ms = 450) { // simulated packet visualisation (NOT real traffic)
    cy.elements().removeClass('path');
    for (const id of path) cy.getElementById(id).addClass('path');
    for (let i = 0; i < path.length - 1; i++) {
      const a = cy.getElementById(path[i]), b = cy.getElementById(path[i + 1]);
      a.edgesWith(b).addClass('path');
    }
    const pkt = cy.add({ group: 'nodes', data: { id: '__pkt' }, classes: 'pkt', position: Object.assign({}, cy.getElementById(path[0]).position()), grabbable: false });
    for (let i = 1; i < path.length; i++) {
      const tgt = cy.getElementById(path[i]).position();
      await new Promise(res => pkt.animate({ position: { x: tgt.x, y: tgt.y } }, { duration: ms, complete: res }));
    }
    pkt.remove(); setTimeout(() => cy.elements().removeClass('path'), 1500);
  },
  fmtTime(s) { try { return new Date(s + 'Z').toLocaleTimeString(); } catch (e) { return s; } },
};
window.NP_READY = new Promise(res => document.addEventListener('DOMContentLoaded', () => res(NP.ensureNetwork())));
