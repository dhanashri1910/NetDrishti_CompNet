(function () {
  const $ = s => document.querySelector(s); let proto = 'tcp';
  $('#sGo').onclick = async () => {
    try {
      const r = await NP.api('/api/subnet', { json: { ip: $('#sIp').value, mask: $('#sMask').value, prefix: $('#sMask').value ? null : $('#sPre').value } });
      const rows = [['Network address', r.network], ['Subnet mask', r.mask], ['CIDR', r.cidr], ['Wildcard', r.wildcard], ['Broadcast address', r.broadcast], ['First usable IP', r.first_usable], ['Last usable IP', r.last_usable], ['Total addresses', r.total_addresses], ['Usable hosts', r.usable_hosts], ['Address type', r.ip_class]];
      $('#sOut').innerHTML = `<table class="table table-sm"><tbody>${rows.map(([a, b]) => `<tr><th>${a}</th><td class="font-monospace">${b}</td></tr>`).join('')}</tbody></table>`;
    } catch (e) { $('#sOut').innerHTML = ''; }
  };
  async function call(a, body = {}) {
    const r = await NP.api(`/api/sockets/${proto}/${a}`, { json: body });
    $('#kSt').innerHTML = `<span class="dot ${r.running ? 'ok' : 'bad'}"></span>${r.running ? 'running on ' + r.host + ':' + r.port : 'stopped'}`;
    $('#kLog').textContent = r.log.join('\n') || 'No traffic yet.';
    if (r.ok === false) NP.toast(r.message, 'danger'); return r;
  }
  $('#kStart').onclick = () => call('start', { port: $('#kPort').value || null });
  $('#kStop').onclick = () => call('stop');
  $('#kSend').onclick = () => call('send', { message: $('#kMsg').value });
  document.querySelectorAll('#proto a').forEach(a => a.onclick = e => { e.preventDefault(); document.querySelectorAll('#proto a').forEach(x => x.classList.remove('active')); a.classList.add('active'); proto = a.dataset.p; call('status'); });
  call('status');
})();
