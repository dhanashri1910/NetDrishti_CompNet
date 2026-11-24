(async function () {
  const id = await window.NP_READY;
  if (!id) { NP.emptyState(document.getElementById('empty')); return; }
  document.getElementById('builder').classList.remove('d-none');
  const $ = s => document.querySelector(s);
  let topo = (await NP.api('/api/networks/' + id)).topology, cy, connect = false, pending = null, selected = null, counter = 100;
  const prefix = { pc: 'PC', switch: 'SW', router: 'R', server: 'Server' };

  function render() {
    if (cy) syncPos();
    if (!cy) { cy = NP.makeCy($('#cy'), topo); bind(); } else { cy.elements().remove(); cy.add(NP.toElements(topo)); }
    fillPing();
    if (selected) { const e = cy.getElementById(selected); if (e.nonempty()) e.select(); else { selected = null; props(); } }
  }
  function syncPos() { cy.nodes().forEach(n => { const d = topo.devices.find(x => x.id === n.id()); if (d) { d.x = Math.round(n.position().x); d.y = Math.round(n.position().y); } }); }
  function bind() {
    cy.on('tap', 'node', e => {
      const n = e.target;
      if (connect) {
        if (!pending) { pending = n.id(); n.addClass('src'); $('#hint').textContent = 'Now click the second device to finish the link.'; }
        else { addLink(pending, n.id()); cy.nodes().removeClass('src'); pending = null; $('#hint').textContent = 'Link created. Click another device to start a new link, or leave Connect mode.'; }
      }
    });
    cy.on('select unselect', () => { const s = cy.$(':selected'); selected = s.length === 1 ? s[0].id() : null; props(); });
    cy.on('tap', e => { if (e.target === cy && connect && pending) { cy.nodes().removeClass('src'); pending = null; } });
  }
  function addLink(a, b) {
    if (a === b) return NP.toast('A device cannot be linked to itself.', 'danger');
    if (topo.links.some(l => (l.source === a && l.target === b) || (l.source === b && l.target === a))) return NP.toast('These devices are already linked.', 'danger');
    topo.links.push({ id: 'l' + (++counter) + Date.now() % 1000, source: a, target: b, up: true, cost: 1 }); render();
    NP.toast('Link created. Save to keep it.', 'success');
  }
  function addDevice(t) {
    const n = topo.devices.filter(d => d.type === t).length + 1;
    const d = { id: t + (++counter) + Date.now() % 1000, name: prefix[t] + n, type: t, x: 120 + Math.random() * 380, y: 80 + Math.random() * 280, up: true, ifaces: [], gateway: '', dns: '' };
    if (t === 'pc' || t === 'server') d.ifaces = [{ name: 'eth0', ip: '', mask: '255.255.255.0', vlan: 1, up: true }];
    if (t === 'router') { d.ifaces = [{ name: 'Gi0/0', ip: '', mask: '255.255.255.0', vlan: 1, up: true }, { name: 'Gi0/1', ip: '', mask: '255.255.255.0', vlan: 1, up: true }]; d.routes = []; }
    if (t === 'switch') d.vlans = [1];
    if (t === 'server') { d.services = []; d.records = {}; }
    topo.devices.push(d); render(); cy.getElementById(d.id).select();
  }
  function del() {
    const s = cy.$(':selected'); if (!s.length) return NP.toast('Select a device or link first.', 'danger');
    s.forEach(e => { const i = e.id(); if (e.isNode()) { topo.devices = topo.devices.filter(d => d.id !== i); topo.links = topo.links.filter(l => l.source !== i && l.target !== i); } else topo.links = topo.links.filter(l => l.id !== i); });
    selected = null; render(); props();
  }
  function props() {
    const el = $('#props');
    if (!selected) { el.innerHTML = 'Select a device or link.'; return; }
    const l = topo.links.find(x => x.id === selected);
    if (l) {
      const nm = i => topo.devices.find(d => d.id === i).name;
      el.innerHTML = `<div class="mb-2"><b>${NP.esc(nm(l.source))} ↔ ${NP.esc(nm(l.target))}</b></div>
        <div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" id="lUp" ${l.up !== false ? 'checked' : ''}><label class="form-check-label" for="lUp">Link up</label></div>
        <label class="form-label mb-0">Routing cost</label><input id="lCost" type="number" min="1" class="form-control form-control-sm mb-2" value="${l.cost || 1}">
        <button class="btn btn-sm btn-np" id="apply">Apply</button>`;
      $('#apply').onclick = () => { l.up = $('#lUp').checked; l.cost = Math.max(1, +$('#lCost').value || 1); render(); NP.toast('Applied'); };
      return;
    }
    const d = topo.devices.find(x => x.id === selected); if (!d) return;
    let h = `<label class="form-label mb-0">Name</label><input id="dName" class="form-control form-control-sm mb-2" value="${NP.esc(d.name)}">
      <div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" id="dUp" ${d.up !== false ? 'checked' : ''}><label class="form-check-label" for="dUp">Device powered on</label></div>`;
    (d.ifaces || []).forEach((i, k) => {
      h += `<div class="border rounded p-2 mb-2" style="border-color:var(--line)!important"><div class="small mb-1 text-info">${NP.esc(i.name)}</div>
        <div class="row g-1"><div class="col-7"><input class="form-control form-control-sm" data-k="${k}" data-f="ip" placeholder="IP address" value="${NP.esc(i.ip)}"></div>
        <div class="col-5"><input class="form-control form-control-sm" data-k="${k}" data-f="mask" placeholder="Mask" value="${NP.esc(i.mask)}"></div>
        <div class="col-5"><input class="form-control form-control-sm" data-k="${k}" data-f="vlan" type="number" placeholder="VLAN" value="${i.vlan ?? 1}"></div>
        <div class="col-7 pt-1"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" data-k="${k}" data-f="up" ${i.up !== false ? 'checked' : ''}><label class="form-check-label small">Interface up</label></div></div></div></div>`;
    });
    if (d.type === 'pc' || d.type === 'server') h += `<label class="form-label mb-0">Default gateway</label><input id="dGw" class="form-control form-control-sm mb-2" value="${NP.esc(d.gateway || '')}">
      <label class="form-label mb-0">DNS server</label><input id="dDns" class="form-control form-control-sm mb-2" value="${NP.esc(d.dns || '')}">`;
    if (d.type === 'switch') h += `<label class="form-label mb-0">VLANs carried (comma separated)</label><input id="dVlans" class="form-control form-control-sm mb-2" value="${(d.vlans || []).join(',')}">`;
    if (d.type === 'router') h += `<div class="small text-secondary mb-1">Connected routes are generated from interface IPs. Extra static routes (one per line: <code>10.0.0.0/8 via 192.168.1.2</code>):</div>
      <textarea id="dStatic" rows="2" class="form-control form-control-sm mb-2">${(d.routes || []).filter(r => r.via !== 'connected').map(r => r.dest + ' via ' + r.via).join('\n')}</textarea>`;
    if (d.type === 'server') h += `<label class="form-label mb-0">Services</label><div class="mb-2"><label class="me-3"><input type="checkbox" id="sDns" ${(d.services || []).includes('dns') ? 'checked' : ''}> DNS</label><label><input type="checkbox" id="sHttp" ${(d.services || []).includes('http') ? 'checked' : ''}> HTTP</label></div>
      <label class="form-label mb-0">DNS records (name=ip per line)</label><textarea id="dRec" rows="3" class="form-control form-control-sm mb-2">${Object.entries(d.records || {}).map(([k, v]) => k + '=' + v).join('\n')}</textarea>`;
    el.innerHTML = h + `<button class="btn btn-sm btn-np" id="apply">Apply</button>`;
    $('#apply').onclick = () => applyDevice(d);
  }
  function applyDevice(d) {
    d.name = $('#dName').value.trim() || d.name; d.up = $('#dUp').checked;
    document.querySelectorAll('#props [data-k]').forEach(inp => { const i = d.ifaces[+inp.dataset.k], f = inp.dataset.f; i[f] = f === 'up' ? inp.checked : f === 'vlan' ? (+inp.value || 1) : inp.value.trim(); });
    if ($('#dGw')) { d.gateway = $('#dGw').value.trim(); d.dns = $('#dDns').value.trim(); }
    if ($('#dVlans')) d.vlans = $('#dVlans').value.split(',').map(x => parseInt(x)).filter(Boolean);
    if (d.type === 'router') {
      const st = ($('#dStatic').value || '').split('\n').map(l => l.trim()).filter(Boolean).map(l => { const m = l.match(/^(\S+)\s+via\s+(\S+)/i); return m ? { dest: m[1], via: m[2], iface: '' } : null; }).filter(Boolean);
      d.routes = d.ifaces.filter(i => i.ip && i.mask).map(i => ({ dest: netOf(i.ip, i.mask), via: 'connected', iface: i.name })).filter(r => r.dest).concat(st);
    }
    if (d.type === 'server') {
      d.services = [$('#sDns').checked && 'dns', $('#sHttp').checked && 'http'].filter(Boolean);
      d.records = {}; ($('#dRec').value || '').split('\n').forEach(l => { const [k, v] = l.split('='); if (k && v) d.records[k.trim().toLowerCase()] = v.trim(); });
    }
    render(); NP.toast('Applied. Save to keep changes.');
  }
  function netOf(ip, mask) {
    const p = s => s.split('.').map(Number); const a = p(ip), m = p(mask);
    if (a.length !== 4 || m.length !== 4 || [...a, ...m].some(x => isNaN(x) || x < 0 || x > 255)) return '';
    const bits = m.map(x => x.toString(2).padStart(8, '0')).join(''); if (!/^1*0*$/.test(bits)) return '';
    return a.map((x, i) => x & m[i]).join('.') + '/' + bits.replace(/0/g, '').length;
  }
  async function save(baseline = false) {
    syncPos();
    await NP.api('/api/networks/' + id, { method: 'PUT', json: { topology: topo, set_baseline_now: baseline } });
    NP.toast(baseline ? 'Saved and set as healthy baseline' : 'Topology saved', 'success');
  }
  function fillPing() {
    const s = $('#pSrc'), v = s.value;
    s.innerHTML = topo.devices.filter(d => d.type === 'pc' || d.type === 'server').map(d => `<option value="${d.id}">${NP.esc(d.name)}</option>`).join(''); if (v) s.value = v;
  }
  document.querySelectorAll('[data-add]').forEach(b => b.onclick = () => addDevice(b.dataset.add));
  $('#btnConnect').onclick = e => { connect = !connect; pending = null; cy.nodes().removeClass('src'); e.currentTarget.classList.toggle('active', connect); $('#hint').textContent = connect ? 'Connect mode: click the first device.' : 'Connect mode off.'; };
  $('#btnLinkSel').onclick = () => { const s = cy.nodes(':selected'); if (s.length !== 2) return NP.toast('Select exactly two devices (Shift+click).', 'danger'); addLink(s[0].id(), s[1].id()); };
  $('#btnDelete').onclick = del;
  document.addEventListener('keydown', e => { if (e.key === 'Delete' && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) del(); });
  $('#btnSave').onclick = () => save(false);
  $('#btnBaseline').onclick = () => save(true);
  $('#btnNew').onclick = async () => { const name = prompt('Name for the new network:'); if (!name) return; const r = await NP.api('/api/networks', { json: { name } }); localStorage.setItem('np_net', r.id); location.reload(); };
  $('#btnPing').onclick = async () => {
    const target = $('#pDst').value.trim(); if (!target) return NP.toast('Enter a target IP or hostname.', 'danger');
    await save(false);
    const r = await NP.api(`/api/networks/${id}/ping`, { json: { src: $('#pSrc').value, target } });
    const box = $('#pRes'); box.classList.remove('d-none');
    box.innerHTML = `${r.ok ? '✔' : '✘'} <b>${r.ok ? 'Reply received' : 'Ping failed'}</b> <span class="sim-tag">simulated</span>\n${NP.esc(r.reason)}\n` +
      (r.ok ? `Path: ${r.path.map(p => NP.esc(topo.devices.find(d => d.id === p)?.name || p)).join(' → ')}\nHops: ${r.hops}  Latency: ${r.latency_ms} ms  Loss: ${r.loss_pct}%` : (r.code ? `Fault hint: ${r.code}` : ''));
    if (r.path && r.path.length > 1) NP.animatePath(cy, r.path);
  };
  render();
})();
