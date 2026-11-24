(async function () {
  const id = await window.NP_READY;
  if (!id) { NP.emptyState(document.getElementById('empty')); return; }
  document.getElementById('lab').classList.remove('d-none');
  const $ = s => document.querySelector(s), E = NP.esc;
  let topo, cy, faultsByDev = {};
  const cat = await NP.api('/api/catalog');
  $('#fCode').innerHTML = Object.entries(cat).map(([k, v]) => `<option value="${k}">${k} – ${v.name}</option>`).join('');
  const STEPS = ['Inject', 'Detect', 'Diagnose', 'Recommend', 'Approve', 'Repair', 'Retest', 'Report'];
  function steps(n) { $('#steps').innerHTML = STEPS.map((s, i) => `<span class="chip" style="${i < n ? 'color:#22d3ee;border-color:#22d3ee' : ''}">${i + 1}. ${s}</span>`).join(''); }
  steps(0);
  async function loadTopo() {
    topo = (await NP.api('/api/networks/' + id)).topology;
    $('#fDev').innerHTML = topo.devices.map(d => `<option value="${d.id}">${E(d.name)} (${d.type})</option>`).join('');
    if (cy) cy.destroy(); cy = NP.makeCy($('#cy'), topo, { faults: faultsByDev });
  }
  const scen = await NP.api('/api/scenarios');
  $('#scen').innerHTML = scen.map((s, i) => `<button class="btn btn-sm btn-outline-info" data-i="${i}" title="${E(s.title)}">${s.code} · ${E(s.title)}</button>`).join('');
  $('#scen').onclick = e => { const b = e.target.closest('button'); if (!b) return; const s = scen[+b.dataset.i]; $('#fCode').value = s.code; $('#fDev').value = s.device; inject(); };
  async function inject() {
    const r = await NP.api(`/api/networks/${id}/faults/inject`, { json: { code: $('#fCode').value, device: $('#fDev').value } });
    NP.toast(`Fault injected: ${r.description} (health ${r.health}%)`, 'danger'); steps(1); faultsByDev = {}; $('#faults').innerHTML = ''; await loadTopo(); await detect();
  }
  async function detect() {
    const r = await NP.api(`/api/networks/${id}/faults/detect?ai=${$('#useAi').checked ? 1 : 0}`);
    faultsByDev = {}; r.faults.forEach(f => faultsByDev[f.device_id] = true); await loadTopo();
    steps(r.faults.length ? 4 : 1);
    $('#faults').innerHTML = r.faults.length ? r.faults.map(card).join('') : `<div class="card-np"><span class="dot ok"></span>No faults detected. Network health ${r.health}%.</div>`;
  }
  function card(f) {
    const dg = f.diagnosis, v = f.fix.value !== undefined ? f.fix.value : null;
    return `<div class="card-np mb-3" data-id="${f.id}">
      <div class="d-flex align-items-center gap-2 mb-2"><span class="sev ${f.severity}">${f.severity}</span><b>${f.code} · ${E(f.name)}</b><span class="ms-auto small text-secondary">${E(f.device_name)}</span></div>
      <p class="mb-2">${E(f.description)}</p>
      <div class="small mb-2"><b>Probable cause:</b> ${E(f.probable_cause)}<br><b>Root cause:</b> ${E(dg.root_cause)}<br><b>Explanation:</b> ${E(dg.explanation)}<br><b>Recommended:</b> ${E(f.recommendation)}<br><b>Expected result:</b> ${E(dg.expected_result)}</div>
      ${dg.ai_text ? `<div class="small p-2 mb-2 rounded" style="background:#0c1429"><b>AI explanation:</b> ${E(dg.ai_text)}</div>` : ''}
      ${v !== null ? `<div class="input-group input-group-sm mb-2"><span class="input-group-text">Correction (editable)</span><input class="form-control fix-val" value="${E(v)}"></div>` : ''}
      <div class="d-flex gap-2"><button class="btn btn-sm btn-success" data-act="approve"><i class="fa-solid fa-check"></i> Approve repair</button>
      <button class="btn btn-sm btn-outline-secondary" data-act="reject"><i class="fa-solid fa-xmark"></i> Reject</button></div></div>`;
  }
  $('#faults').onclick = async e => {
    const b = e.target.closest('button[data-act]'); if (!b) return;
    const c = b.closest('[data-id]'), val = c.querySelector('.fix-val')?.value;
    const r = await NP.api(`/api/faults/${c.dataset.id}/decision`, { json: { decision: b.dataset.act, value: val } });
    if (b.dataset.act === 'reject') { NP.toast('Repair rejected – fault left open.'); c.style.opacity = .5; return; }
    steps(8); showRecovery(c.querySelector('b').textContent, r); NP.toast(r.resolved ? 'Recovered: ' + r.action : 'Repair applied but fault persists', r.resolved ? 'success' : 'danger');
    await detect(); steps(8);
  };
  function showRecovery(title, r) {
    $('#recWrap').classList.remove('d-none');
    const rowset = m => m.rows.map(x => `<tr><td>${E(x.src_name)} → ${E(x.dst_name)}</td><td>${x.ok ? '<span class="dot ok"></span>OK' : '<span class="dot bad"></span>FAIL'}</td></tr>`).join('');
    $('#rec').insertAdjacentHTML('afterbegin', `<div class="mb-4"><div class="mb-2"><b>${E(title)}</b> — ${E(r.action)} · <span class="${r.resolved ? 'text-success' : 'text-danger'}">${r.resolved ? 'Recovery verified' : 'Not resolved'}</span> <span class="sim-tag">simulated</span></div>
      <div class="row g-3"><div class="col-md-6"><div class="small mb-1">Before: health <b>${r.before.health}%</b> (${r.before.ok}/${r.before.total})</div><table class="table table-sm"><tbody>${rowset(r.before)}</tbody></table></div>
      <div class="col-md-6"><div class="small mb-1">After: health <b>${r.after.health}%</b> (${r.after.ok}/${r.after.total})</div><table class="table table-sm"><tbody>${rowset(r.after)}</tbody></table></div></div></div>`);
  }
  $('#bInject').onclick = inject; $('#bDetect').onclick = detect;
  $('#bReset').onclick = async () => { await NP.api(`/api/networks/${id}/reset`, { json: {} }); faultsByDev = {}; $('#faults').innerHTML = ''; steps(0); await loadTopo(); NP.toast('Network restored to baseline', 'success'); };
  await loadTopo();
})();
