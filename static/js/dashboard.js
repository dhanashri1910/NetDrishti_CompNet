(async function () {
  const id = await window.NP_READY;
  if (!id) { document.getElementById('empty').innerHTML = ''; NP.emptyState(document.getElementById('empty')); return; }
  Chart.defaults.color = '#8b9bc4'; Chart.defaults.borderColor = '#243158';
  let cH, cL;
  async function load() {
    const d = await NP.api('/api/dashboard?network=' + id);
    if (d.empty) return;
    document.getElementById('dash').classList.remove('d-none');
    const k = (v, l, c = '') => `<div class="col-6 col-md-3 col-xl"><div class="card-np kpi ${c}"><span class="v">${v}</span><span class="l">${l}</span></div></div>`;
    document.getElementById('kpis').innerHTML =
      k(d.health + '%', 'Network health score', d.health >= 90 ? 'ok' : d.health >= 60 ? 'cy' : 'bad') + k(d.devices, 'Total devices') + k(d.active_devices, 'Active devices', 'ok') +
      k(d.failed_devices, 'Failed devices', d.failed_devices ? 'bad' : '') + k(`${d.active_links}/${d.links}`, 'Active links', 'cy') +
      k(d.detected, 'Faults detected', 'pu') + k(d.recovered, 'Faults recovered', 'ok');
    const hist = d.history.length ? d.history : [{ t: 'now', health: d.health }];
    const dsH = { labels: hist.map(h => h.t), datasets: [{ label: 'Health %', data: hist.map(h => h.health), borderColor: '#22d3ee', backgroundColor: 'rgba(34,211,238,.15)', fill: true, tension: .3 }] };
    if (cH) { cH.data = dsH; cH.update(); } else cH = new Chart(document.getElementById('cHealth'), { type: 'line', data: dsH, options: { maintainAspectRatio: false, scales: { y: { min: 0, max: 100 } } } });
    const lat = d.latency.filter(x => !x.pair.includes('DNS'));
    const dsL = { labels: lat.map(x => x.pair), datasets: [{ label: 'Latency (ms)', data: lat.map(x => x.ms ?? 0), backgroundColor: lat.map(x => x.ok ? '#3b82f6' : '#ef4444'), yAxisID: 'y' },
      { label: 'Throughput (Mbps)', type: 'line', data: lat.map(x => x.mbps), borderColor: '#a78bfa', yAxisID: 'y1', tension: .3 }] };
    if (cL) { cL.data = dsL; cL.update(); } else cL = new Chart(document.getElementById('cLat'), { type: 'bar', data: dsL, options: { maintainAspectRatio: false, scales: { y: { title: { display: true, text: 'ms' } }, y1: { position: 'right', grid: { drawOnChartArea: false } }, x: { ticks: { display: false } } } } });
    document.getElementById('alerts').innerHTML = d.alerts.length ? d.alerts.map(a => `<div class="feed-item"><span class="sev ${a.severity}">${a.code}</span><div>${NP.esc(a.device)}<br><small class="d-block ms-0 text-secondary">${NP.esc(a.desc)}</small></div></div>`).join('') : '<span class="text-secondary">No open faults. Go to the Fault Lab to inject one.</span>';
    document.getElementById('feed').innerHTML = d.feed.map(f => `<div class="feed-item"><span>${NP.esc(f.msg)}</span><small>${f.t}</small></div>`).join('') || '<span class="text-secondary">No activity yet.</span>';
    const typeRows = Object.entries(d.device_types || {}).map(([type, count]) =>
      `<div class="d-flex justify-content-between py-1 border-bottom border-secondary-subtle"><span class="text-capitalize">${NP.esc(type)}</span><strong>${count}</strong></div>`
    ).join('');
    document.getElementById('topologySummary').innerHTML =
      `<div class="mb-2"><strong>${NP.esc(d.name)}</strong></div>
       ${typeRows || '<span class="text-secondary">No devices in this topology.</span>'}
       <div class="d-flex justify-content-between mt-2"><span>Connections</span><strong>${d.active_links}/${d.links} active</strong></div>
       <div class="d-flex justify-content-between"><span>Network health</span><strong>${d.health}%</strong></div>`;
    document.getElementById('loss').textContent = d.loss;
  }
  load(); setInterval(load, 10000);
})();
