'use strict';
const $ = s => document.querySelector(s),
  $$ = s => [...document.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
} [c]));
const shapes = {
  lattice: '<path d="m12 2 9 5v10l-9 5-9-5V7Z M3 7l18 10 M21 7 3 17 M12 2v20"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="m16 8-3 5-5 3 3-5Z"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8Z M2 12l10 5 10-5 M2 16l10 5 10-5"/>',
  file: '<path d="M14 2H5v20h14V7Z M14 2v5h5 M8 12h8 M8 16h6"/>',
  settings: '<path d="M4 7h16 M4 17h16"/><circle cx="8" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
  plus: '<path d="M12 5v14 M5 12h14"/>',
  terminal: '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="m6 9 3 3-3 3 M12 15h5"/>',
  book: '<path d="M12 5v16 M12 5C8 2 4 3 2 4v16c4-2 7-1 10 1 3-2 6-3 10-1V4c-4-2-7-1-10 1Z"/>',
  sparkles: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z M20 1v5 M17.5 3.5h5"/>',
  github: '<path d="M9 20c-4 1-4-2-6-2 M9 22v-4c-6 0-7-9-3-11 0-1 0-3 1-4l4 2h2l4-2c1 1 1 3 1 4 4 2 3 11-3 11v4"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3 M15 2v3 M9 19v3 M15 19v3 M2 9h3 M2 15h3 M19 9h3 M19 15h3"/>',
  activity: '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  download: '<path d="M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5"/>',
  compare: '<path d="M3 7h17l-4-4 M21 17H4l4 4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6 M12 7v1"/>',
  link: '<path d="m10 13 4-4 M8 15l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0 M16 9l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0"/>',
  panel: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M15 3v18"/>',
  'arrow-up': '<path d="M12 20V4 m-6 6 6-6 6 6"/>',
  search: '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4 M12 14v3"/>',
  play: '<path d="m7 4 14 8-14 8Z"/>',
  x: '<path d="m6 6 12 12 M18 6 6 18"/>'
};
shapes.sliders = shapes.settings;
const icon = name => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (shapes[name] || shapes.lattice) + '</svg>';
$$('[data-icon]').forEach(el => el.innerHTML = icon(el.dataset.icon));
const DEFAULT = {
  title: 'Surface-code noise investigation',
  question: 'How does code distance affect logical memory performance?',
  distances: [3, 5, 7],
  probabilities: [.001, .003, .005, .007, .01],
  rounds: 5,
  shots: 10000,
  measurement_multiplier: 1,
  decoder: 'matched',
  seed: 42,
  budget_seconds: 120
};
const state = {
  spec: structuredClone(DEFAULT),
  run: null,
  runs: [],
  comparison: null,
  selected: null,
  scale: 'log',
  hidden: new Set(),
  health: null,
  view: 'investigation',
  tab: 'results',
  poll: null,
  chatBusy: false,
  loadToken: 0
};
const colors = {
  3: '#08786d',
  5: '#9b80be',
  7: '#d69a59',
  9: '#557fb1'
};
const fmt = n => Number(n).toLocaleString(),
  pct = n => (n * 100).toLocaleString(undefined, {
    maximumFractionDigits: 3
  }) + '%',
  rate = n => n === 0 ? '0 observed' : n.toExponential(2);
const active = r => r && ['queued', 'running', 'cancelling'].includes(r.status);

function notify(text) {
  $('#toast').textContent = text;
  $('#toast').classList.add('visible');
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 4500);
}
async function api(path, options = {}) {
  const r = await fetch('/api' + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  });
  if (!r.ok) {
    let d;
    try {
      d = await r.json();
    } catch {
      throw Error('The server could not complete this request.');
    }
    throw Error(Array.isArray(d.detail) ? d.detail.map(x => x.msg).join(' · ') : d.detail || 'Request failed');
  }
  return r.json();
}
const post = (path, data) => api(path, {
  method: 'POST',
  body: JSON.stringify(data)
});

function on(sel, event, fn) {
  $(sel).addEventListener(event, e => Promise.resolve(fn(e)).catch(err => notify(err.message)));
}

function view(name) {
  state.view = name;
  ['investigation', 'history', 'reports', 'settings'].forEach(v => $('#' + v + '-view').hidden = v !== name);
  $$('[data-nav]').forEach(b => b.classList.toggle('active', b.dataset.nav === name));
  $('#breadcrumb').textContent = {
    investigation: 'Investigation',
    history: 'Run history',
    reports: 'Reports & artifacts',
    settings: 'Settings'
  } [name];
  if (name === 'history') renderHistory();
  if (name === 'reports') renderReports();
}

function tab(name) {
  state.tab = name;
  ['results', 'explorer', 'activity'].forEach(v => $('#' + v + '-panel').hidden = v !== name);
  $$('[data-tab]').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === name);
    b.setAttribute('aria-selected', String(b.dataset.tab === name));
    b.tabIndex = b.dataset.tab === name ? 0 : -1;
  });
  if (name === 'explorer') renderExplorer();
  if (name === 'activity') renderActivity();
}
$$('[data-nav]').forEach(b => b.addEventListener('click', () => view(b.dataset.nav)));
$$('[data-tab]').forEach(b => b.addEventListener('click', () => tab(b.dataset.tab)));
on('.tabs', 'keydown', e => {
  if (['ArrowLeft', 'ArrowRight'].includes(e.key) && e.target.matches('[data-tab]')) {
    e.preventDefault();
    const a = $$('[data-tab]'),
      b = a[(a.indexOf(e.target) + (e.key === 'ArrowRight' ? 1 : 2)) % 3];
    tab(b.dataset.tab);
    b.focus();
  }
});

function showAssistant(show) {
  const p = $('#assistant-panel');
  if (matchMedia('(max-width:1080px)').matches) {
    p.hidden = false;
    p.classList.toggle('mobile-open', show);
  } else p.hidden = !show;
  $('#toggle-assistant').setAttribute('aria-expanded', String(show));
}
on('#toggle-assistant', 'click', () => showAssistant(matchMedia('(max-width:1080px)').matches ? !$('#assistant-panel').classList.contains('mobile-open') : $('#assistant-panel').hidden));
on('#close-assistant', 'click', () => showAssistant(false));

function renderHealth() {
  const h = state.health;
  $('#connection').innerHTML = '<i></i>Local engine ready';
  $('#connection').classList.remove('offline');
  $('#engine-label').textContent = 'Stim ' + h.environment.stim + ' · PyMatching ' + h.environment.pymatching;
  $('#gemini-status').textContent = h.gemini_connected ? 'Key configured' : 'Not connected';
  $('#assistant-provider').textContent = h.gemini_connected ? 'Gemini · tools enabled' : 'Gemini · connection required';
  $('#assistant-notice').textContent = h.gemini_connected ? 'Questions include your plan and selected run. Check AI conclusions against the evidence.' : 'Connect Gemini in Settings to ask a question. Manual experiments are ready to run.';
  $('#model-name').textContent = h.model;
  $('#engine-versions').innerHTML = ['python', 'stim', 'pymatching', 'numpy', 'machine', 'schema_version'].map(k => '<span>' + esc(k.replace('_', ' ')) + '<strong>' + esc(h.environment[k]) + '</strong></span>').join('');
}
async function refreshRuns() {
  state.runs = await api('/runs');
  $('#run-count').textContent = state.runs.length;
  $('#recent-runs').innerHTML = state.runs.slice(0, 4).map(r => '<button class="recent-button ' + (r.id === state.run?.id ? 'selected' : '') + '" data-run="' + r.id + '"><i></i><span>' + esc(r.spec.title) + '</span></button>').join('') || '<p class="sidebar-hint">Your investigations will appear here.</p>';
  const el = $('#compare-run'),
    selected = el.value;
  el.innerHTML = '<option value="">Compare a run</option>' + state.runs.filter(r => r.id !== state.run?.id && r.point_count).map(r => '<option value="' + r.id + '">' + esc(r.spec.title) + ' · ' + r.id.slice(0, 6) + '</option>').join('');
  el.value = selected;
  if (state.view === 'history') renderHistory();
  if (state.view === 'reports') renderReports();
}
async function loadRun(id) {
  const token = ++state.loadToken;
  clearTimeout(state.poll);
  const r = await api('/runs/' + id);
  if (token !== state.loadToken) return;
  state.run = r;
  state.spec = structuredClone(r.spec);
  state.selected = r.points.find(p => p.failure)?.id || r.points[0]?.id || null;
  state.comparison = null;
  state.hidden.clear();
  $('#compare-run').value = '';
  view('investigation');
  renderRun();
  history.replaceState(null, '', '#run=' + id);
  await refreshRuns();
  await loadChat();
  pollRun();
}

function pollRun() {
  clearTimeout(state.poll);
  if (!active(state.run)) return;
  const id = state.run.id;
  state.poll = setTimeout(async () => {
    try {
      const r = await api('/runs/' + id);
      if (state.run?.id !== id) return;
      state.run = r;
      renderRun();
      if (!active(r)) {
        await refreshRuns();
        notify('Investigation ' + r.status.replaceAll('_', ' '));
      }
      pollRun();
    } catch (err) {
      notify(err.message);
      state.poll = setTimeout(pollRun, 3000);
    }
  }, 900);
}

function selectedPoint() {
  return state.run?.points.find(p => p.id === state.selected);
}

function renderRun() {
  const r = state.run,
    s = r?.spec || state.spec,
    points = r?.points.filter(p => p.shots) || [];
  $('#investigation-title').textContent = r ? s.title : 'Explore beyond the physical qubit.';
  $('#investigation-question').textContent = r ? s.question : 'Configure a surface-code experiment. Turn a question into evidence.';
  $('#run-short').textContent = r ? 'RUN ' + r.id.slice(0, 8).toUpperCase() : 'NEW INVESTIGATION';
  $('#run-status').textContent = r ? r.status.replaceAll('_', ' ') : 'Ready to investigate';
  $('#run-status').className = 'pill ' + (r?.status || '');
  $('#saved-label').textContent = r ? new Date(r.created).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric'
  }) + ' · saved locally' : 'Fixed-shot sampling';
  $('#export-run').disabled = !r;
  $('#execution-progress').hidden = !active(r);
  $('#progress-bar').value = r?.progress || 0;
  $('#progress-message').textContent = r ? Math.round(r.progress * 100) + '% · ' + fmt(points.reduce((n, p) => n + p.shots, 0)) + ' shots sampled · ' + r.status : '';
  const best = points.length ? points.reduce((a, b) => a.rate < b.rate ? a : b) : null;
  $('#metric-rate').textContent = best ? rate(best.rate) : '—';
  $('#metric-rate-note').textContent = best ? 'd = ' + best.distance + ' · p = ' + pct(best.p) + (best.complete ? '' : ' · provisional') : 'Measured per memory experiment';
  $('#metric-shots').textContent = fmt(points.reduce((n, p) => n + p.shots, 0));
  $('#metric-shots-note').textContent = points.length ? points.filter(p => p.complete).length + ' / ' + s.distances.length * s.probabilities.length + ' configurations complete' : 'Every shot backed by a recorded seed';
  $('#metric-time').textContent = r ? r.elapsed.toFixed(1) + ' s' : '—';
  $('#metric-time-note').textContent = 'Budget ' + s.budget_seconds + ' s · local worker';
  $('#assistant-context').textContent = r ? 'Context: run ' + r.id.slice(0, 8) : 'Context: current experiment plan';
  $('#spec-summary').innerHTML = '<dl>' + [
    ['Code distances', s.distances.join(', ')],
    ['Syndrome rounds', s.rounds],
    ['Shots per point', fmt(s.shots)],
    ['Measurement noise', s.measurement_multiplier + ' × p'],
    ['Decoder weights', s.decoder],
    ['Sampling seed', s.seed]
  ].map(([k, v]) => '<dt>' + k + '</dt><dd>' + esc(v) + '</dd>').join('') + '</dl>';
  if (!points.some(p => p.id === state.selected)) state.selected = points[0]?.id || null;
  renderChart();
  renderPoint();
  renderActivity();
  if (state.tab === 'explorer') renderExplorer();
}
const superscript = n => String(n).split('').map(c => ({
  '-': '⁻',
  '0': '⁰',
  '1': '¹',
  '2': '²',
  '3': '³',
  '4': '⁴',
  '5': '⁵',
  '6': '⁶',
  '7': '⁷',
  '8': '⁸',
  '9': '⁹'
} [c])).join('');

function renderChart() {
  const points = state.run?.points.filter(p => p.shots) || [],
    compare = state.comparison?.points.filter(p => p.shots) || [],
    ds = [...new Set([...points, ...compare].map(p => p.distance))].sort((a, b) => a - b);
  $('#chart-legend').innerHTML = (ds.length ? ds : state.spec.distances).map(d => '<button class="legend-button ' + (state.hidden.has(d) ? 'off' : '') + '" style="--series:' + colors[d] + '" data-distance="' + d + '" aria-pressed="' + !state.hidden.has(d) + '"><i></i>d = ' + d + '</button>').join('');
  const note = $('#comparison-note');
  note.hidden = !state.comparison;
  if (state.comparison) {
    const a = state.run.spec,
      b = state.comparison.spec,
      changes = ['rounds', 'shots', 'measurement_multiplier', 'decoder', 'seed'].filter(k => a[k] !== b[k]).map(k => k.replaceAll('_', ' ') + ': ' + a[k] + ' vs ' + b[k]);
    note.textContent = 'Dashed: ' + b.title + '. ' + (changes.length ? 'Differences — ' + changes.join('; ') : 'Same scalar settings; inspect distances and noise grids in each run.') + ' Compare uncertainty, not just curve position.';
  }
  if (!points.length) {
    $('#chart').innerHTML = '<div class="empty-chart">' + icon('lattice') + '<h3>Your next discovery starts here.</h3><p>Run a real simulation to reveal the landscape.</p><button class="button" data-action="configure">Design an experiment ↗</button></div>';
    return;
  }
  const all = [...points, ...compare],
    W = Math.max(280, $('#chart').clientWidth - 24),
    H = $('#chart').clientHeight - 8,
    L = 60,
    R = 26,
    T = 32,
    B = 55,
    cw = W - L - R,
    ch = H - T - B,
    xmin = Math.min(...all.map(p => p.p)),
    xmax = Math.max(...all.map(p => p.p)),
    x = p => L + (xmax === xmin ? .5 : (p - xmin) / (xmax - xmin)) * cw,
    positive = all.flatMap(p => [p.rate, p.interval[0], p.interval[1]]).filter(v => v > 0);
  let ymin = state.scale === 'log' ? 10 ** Math.floor(Math.log10(Math.min(...positive))) : 0,
    ymax = state.scale === 'log' ? Math.min(1, 10 ** Math.ceil(Math.log10(Math.max(...positive)))) : Math.min(1, Math.max(...all.map(p => p.interval[1])) * 1.15);
  if (ymax <= ymin) ymax = ymin * 10;
  if (state.scale === 'linear' && ymax === 0) ymax = .01;
  const y = p => T + ch * (1 - (state.scale === 'log' ? (Math.log10(Math.max(p, ymin)) - Math.log10(ymin)) / (Math.log10(ymax) - Math.log10(ymin)) : (p - ymin) / (ymax - ymin)));
  let html = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Logical error probability versus noise parameter, with 95 percent Wilson intervals. Select a point to inspect."><text class="chart-axis-title" x="' + L + '" y="16">Logical error / memory experiment</text>';
  const ticks = state.scale === 'log' ? Array.from({
    length: Math.round(Math.log10(ymax) - Math.log10(ymin)) + 1
  }, (_, i) => ymin * 10 ** i) : Array.from({
    length: 5
  }, (_, i) => ymax * i / 4);
  ticks.forEach(v => {
    html += '<line class="chart-grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="chart-label" text-anchor="end" x="' + (L - 12) + '" y="' + (y(v) + 4) + '">' + (state.scale === 'log' ? '10' + superscript(Math.round(Math.log10(v))) : pct(v)) + '</text>';
  });
  [...new Set(all.map(p => p.p))].sort((a, b) => a - b).forEach(v => html += '<text class="chart-label" text-anchor="middle" x="' + x(v) + '" y="' + (H - B + 24) + '">' + pct(v) + '</text>');
  html += '<text class="chart-axis-title" text-anchor="middle" x="' + (L + cw / 2) + '" y="' + (H - 5) + '">Physical noise parameter p</text>';

  function series(arr, d, dashed) {
    const pts = arr.filter(p => p.distance === d).sort((a, b) => a.p - b.p);
    if (!pts.length || state.hidden.has(d)) return;
    const c = colors[d];
    let path = '',
      pen = false;
    pts.forEach(p => {
      if (p.rate === 0 && state.scale === 'log') {
        pen = false;
        return;
      }
      path += (pen ? ' L' : ' M') + x(p.p) + ' ' + y(p.rate);
      pen = true;
    });
    html += '<path class="chart-line" stroke="' + c + '" ' + (dashed ? 'stroke-dasharray="5 5" opacity=".55"' : '') + ' d="' + path + '"/>';
    pts.forEach(p => {
      const xx = x(p.p),
        yy = y(p.rate || (state.scale === 'log' ? p.interval[1] : 0)),
        lo = y(p.interval[0]),
        hi = y(p.interval[1]);
      html += '<path class="chart-ci" stroke="' + c + '" d="M' + xx + ' ' + lo + 'V' + hi + ' M' + (xx - 3) + ' ' + lo + 'h6 M' + (xx - 3) + ' ' + hi + 'h6"/>';
      if (dashed) {
        html += '<circle cx="' + xx + '" cy="' + yy + '" r="3" fill="' + c + '" opacity=".4"/>';
        return;
      }
      html += '<g class="plot-point ' + (state.selected === p.id ? 'selected' : '') + '" style="--series:' + c + '" tabindex="0" role="button" aria-label="' + p.id + ': ' + p.errors + ' failures in ' + p.shots + ' shots" data-point="' + p.id + '"><title>' + p.id + ' · ' + p.errors + '/' + p.shots + ' · 95% CI ' + pct(p.interval[0]) + '–' + pct(p.interval[1]) + '</title>';
      if (state.selected === p.id) html += '<circle class="point-halo" cx="' + xx + '" cy="' + yy + '" r="11"/>';
      html += p.rate === 0 && state.scale === 'log' ? '<path fill="' + c + '" d="M' + xx + ' ' + (yy + 5) + 'l-5-9h10Z"/>' : '<circle cx="' + xx + '" cy="' + yy + '" r="4" stroke="' + c + '"/>';
      html += '</g>';
    });
  }
  ds.forEach(d => series(compare, d, true));
  ds.forEach(d => series(points, d, false));
  $('#chart').innerHTML = html + '</svg>';
}

function renderPoint() {
  const p = selectedPoint();
  $('#point-label').textContent = p ? p.id : 'No point selected';
  $('#inspect-failure').disabled = !p?.failure;
  if (!p) {
    $('#point-detail').innerHTML = '<p class="muted">Inspect measured counts, uncertainty, and sampling provenance after your first run.</p>';
    return;
  }
  $('#point-detail').innerHTML = '<div class="point-stats">' + [
    ['Logical failures', fmt(p.errors) + ' / ' + fmt(p.shots)],
    ['Observed probability', rate(p.rate)],
    ['95% Wilson interval', pct(p.interval[0]) + ' – ' + pct(p.interval[1])],
    ['Batch decode time', (p.decode_seconds * 1000).toFixed(1) + ' ms']
  ].map(([k, v]) => '<div><span>' + k + '</span><strong>' + v + '</strong></div>').join('') + '</div><p class="point-note">' + (p.complete ? 'Fixed shot target reached.' : 'Partial samples · provisional interval.') + (p.errors === 0 ? ' No failures observed; the upper limit is not zero.' : '') + ' Timing excludes sampling and graph construction.</p>';
}

function selectPoint(id) {
  state.selected = id;
  renderPoint();
  renderChart();
}
on('#chart', 'click', e => {
  const p = e.target.closest('[data-point]');
  if (p) selectPoint(p.dataset.point);
  if (e.target.closest('[data-action="configure"]')) openPlan();
});
on('#chart', 'keydown', e => {
  const p = e.target.closest('[data-point]');
  if (p && ['Enter', ' '].includes(e.key)) {
    e.preventDefault();
    selectPoint(p.dataset.point);
  }
});
on('#chart-legend', 'click', e => {
  const b = e.target.closest('[data-distance]');
  if (b) {
    const d = +b.dataset.distance;
    state.hidden.has(d) ? state.hidden.delete(d) : state.hidden.add(d);
    renderChart();
  }
});
$$('[data-scale]').forEach(b => b.addEventListener('click', () => {
  state.scale = b.dataset.scale;
  $$('[data-scale]').forEach(el => {
    el.classList.toggle('selected', el === b);
    el.setAttribute('aria-pressed', String(el === b));
  });
  renderChart();
}));
on('#compare-run', 'change', async e => {
  state.comparison = e.target.value ? await api('/runs/' + e.target.value) : null;
  renderChart();
});

function renderExplorer() {
  const pts = state.run?.points.filter(p => p.failure) || [],
    current = $('#failure-point').value;
  $('#failure-point').innerHTML = pts.map(p => '<option value="' + p.id + '">' + p.id + '</option>').join('');
  $('#failure-point').value = pts.some(p => p.id === current) ? current : pts.some(p => p.id === state.selected) ? state.selected : pts[0]?.id || '';
  const p = pts.find(p => p.id === $('#failure-point').value);
  if (!p) {
    $('#detector-view').innerHTML = '<div class="empty-chart">' + icon('lattice') + '<h3>No failed sample to inspect.</h3><p>Choose a run with observed failures.</p></div>';
    $('#failure-detail').innerHTML = '<p>Failures are captured from actual simulation shots. None are available for this investigation yet.</p>';
    $('#round-slider').disabled = true;
    return;
  }
  $('#round-slider').disabled = false;
  const f = p.failure,
    coords = Object.entries(f.coordinates),
    maxT = Math.max(...coords.map(([, v]) => v[2] || 0));
  $('#round-slider').max = maxT;
  const t = Math.min(+$('#round-slider').value, maxT);
  $('#round-output').textContent = t;
  const maxX = Math.max(...coords.map(([, v]) => v[0])),
    maxY = Math.max(...coords.map(([, v]) => v[1])),
    x = v => 35 + v / Math.max(1, maxX) * 300,
    y = v => 35 + v / Math.max(1, maxY) * 250;
  let html = '<svg viewBox="0 0 370 320" role="img" aria-label="Detection events at time slice ' + t + '">';
  coords.filter(([, v]) => (v[2] || 0) === t).forEach(([id, v]) => {
    const fired = f.events.includes(+id);
    html += '<g class="detector-node ' + (fired ? 'fired' : '') + '" tabindex="0" role="button" data-detector="' + id + '" aria-label="Detector ' + id + (fired ? ', event observed' : ', no event') + '"><title>Detector ' + id + ' · (' + v.join(', ') + ')</title><circle cx="' + x(v[0]) + '" cy="' + y(v[1]) + '" r="' + (fired ? 8 : 5) + '"/><text x="' + x(v[0]) + '" y="' + (y(v[1]) + 20) + '" text-anchor="middle" class="chart-label">' + id + '</text></g>';
  });
  $('#detector-view').innerHTML = html + '</svg>';
  $('#failure-detail').innerHTML = '<span class="pill failed">Logical prediction mismatch</span><h3>' + esc(p.id) + '</h3><dl>' + [
    ['Actual observable', f.actual.join(', ')],
    ['Predicted observable', f.predicted.join(', ')],
    ['Detection events', f.events.length],
    ['Batch seed', f.batch_seed],
    ['Shot in batch', f.shot_index + ' (zero-based)']
  ].map(([k, v]) => '<dt>' + k + '</dt><dd>' + esc(v) + '</dd>').join('') + '</dl><p id="detector-selection">Select a detector to see its coordinates and event state.</p>';
}

function inspectDetector(id) {
  const f = state.run.points.find(p => p.id === $('#failure-point').value).failure;
  $('#detector-selection').textContent = 'Detector ' + id + ' · coordinates (' + f.coordinates[id].join(', ') + ') · ' + (f.events.includes(+id) ? 'unexpected parity observed.' : 'no detection event in this shot.');
}
on('#detector-view', 'click', e => {
  const n = e.target.closest('[data-detector]');
  if (n) inspectDetector(n.dataset.detector);
});
on('#detector-view', 'keydown', e => {
  const n = e.target.closest('[data-detector]');
  if (n && ['Enter', ' '].includes(e.key)) {
    e.preventDefault();
    inspectDetector(n.dataset.detector);
  }
});
on('#round-slider', 'input', renderExplorer);
on('#failure-point', 'change', renderExplorer);
on('#inspect-failure', 'click', () => {
  $('#failure-point').innerHTML = '';
  tab('explorer');
});

function renderActivity() {
  $('#activity-list').innerHTML = state.run ? state.run.events.map(e => '<div class="event-row"><time>' + new Date(e.time).toLocaleTimeString() + '</time><p>' + esc(e.message) + '</p></div>').join('') : '<div class="empty-state">Execution events will appear here when you start an investigation.</div>';
  $('#environment').textContent = state.run ? JSON.stringify(state.run.environment, null, 2) : 'No execution environment recorded yet.';
}

function renderHistory() {
  const q = $('#history-search').value.toLowerCase(),
    runs = state.runs.filter(r => (r.spec.title + ' ' + r.id).toLowerCase().includes(q));
  $('#history-count').textContent = runs.length + ' investigations';
  $('#history-table').innerHTML = runs.map(r => '<tr><td><strong>' + esc(r.spec.title) + '</strong><small>' + r.id.slice(0, 8) + '</small></td><td><span class="pill ' + r.status + '">' + r.status.replaceAll('_', ' ') + '</span></td><td>' + r.spec.distances.join(', ') + '</td><td>' + fmt(r.shots_done) + '</td><td>' + new Date(r.created).toLocaleDateString() + '</td><td><button class="text-button" data-run="' + r.id + '">Open ↗</button></td></tr>').join('') || '<tr><td colspan="6" class="empty-state">No matching investigations. Create your first experiment from the workspace.</td></tr>';
}
on('#history-search', 'input', renderHistory);

function renderReports() {
  $('#reports-list').innerHTML = state.runs.filter(r => r.point_count).map(r => '<article class="card report-row"><span class="report-icon">' + icon('file') + '</span><div><h2>' + esc(r.spec.title) + '</h2><p>' + r.id.slice(0, 8) + ' · ' + fmt(r.shots_done) + ' shots · ' + r.status.replaceAll('_', ' ') + '</p></div><div class="report-actions"><a class="button" href="/api/runs/' + r.id + '/report">Report ↓</a><a class="button primary" href="/api/runs/' + r.id + '/export">Reproduction bundle ↓</a></div></article>').join('') || '<div class="card empty-state">Reports become available once an investigation has collected samples.</div>';
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-run]');
  if (b) loadRun(b.dataset.run).catch(err => notify(err.message));
});

function fillPlan(s) {
  $('#plan-title').value = s.title;
  $('#plan-question').value = s.question;
  $$('input[name="distance"]').forEach(el => el.checked = s.distances.includes(+el.value));
  $('#plan-probabilities').value = s.probabilities.map(p => +(p * 100).toFixed(6)).join(', ');
  const select = $('#plan-shots');
  if (![...select.options].some(o => +o.value === s.shots)) select.add(new Option(fmt(s.shots), String(s.shots)));
  select.value = s.shots;
  $('#plan-rounds').value = s.rounds;
  $('#plan-multiplier').value = s.measurement_multiplier;
  $('#plan-decoder').value = s.decoder;
  $('#plan-seed').value = s.seed;
  $('#plan-budget').value = s.budget_seconds;
  $('#plan-error').hidden = true;
  cost();
}

function readPlan() {
  const tokens = $('#plan-probabilities').value.split(',').map(v => v.trim()),
    distances = $$('input[name="distance"]:checked').map(el => +el.value),
    probabilities = tokens.map(v => Number((Number(v) / 100).toPrecision(15)));
  if (!distances.length) throw Error('Select at least one code distance.');
  if (tokens.some(v => !v || !Number.isFinite(Number(v))) || probabilities.length > 6 || probabilities.some(p => p < 0 || p > .05) || new Set(probabilities).size !== probabilities.length) throw Error('Enter up to six unique noise percentages from 0 to 5.');
  return {
    title: $('#plan-title').value.trim(),
    question: $('#plan-question').value.trim(),
    distances,
    probabilities,
    shots: +$('#plan-shots').value,
    rounds: +$('#plan-rounds').value,
    measurement_multiplier: +$('#plan-multiplier').value,
    decoder: $('#plan-decoder').value,
    seed: +$('#plan-seed').value,
    budget_seconds: +$('#plan-budget').value
  };
}

function cost() {
  const n = $$('input[name="distance"]:checked').length * $('#plan-probabilities').value.split(',').length;
  $('#plan-cost').textContent = n + ' configurations · ' + fmt(n * +$('#plan-shots').value) + ' shots';
}
on('#plan-form', 'input', cost);

function openPlan(s = state.spec) {
  fillPlan(s);
  $('#plan-dialog').showModal();
}
on('#open-plan', 'click', () => openPlan());
on('#edit-plan', 'click', () => openPlan());
on('#close-plan', 'click', () => $('#plan-dialog').close());
on('#new-investigation', 'click', async () => openPlan(await api('/draft') || structuredClone(DEFAULT)));
on('#save-plan', 'click', async () => {
  try {
    if (!$('#plan-form').reportValidity()) return;
    const spec = readPlan();
    await post('/draft', spec);
    state.spec = spec;
    state.run = null;
    state.selected = null;
    state.comparison = null;
    state.loadToken++;
    clearTimeout(state.poll);
    $('#plan-dialog').close();
    view('investigation');
    history.replaceState(null, '', '#draft');
    renderRun();
    await loadChat();
    notify('Draft saved to this workspace.');
  } catch (err) {
    $('#plan-error').hidden = false;
    $('#plan-error').textContent = err.message;
  }
});
$$('[data-preset]').forEach(b => b.addEventListener('click', () => {
  const s = structuredClone(DEFAULT);
  if (b.dataset.preset !== 'baseline') {
    s.measurement_multiplier = 3;
    s.title = 'Measurement-noise stress test';
    s.question = 'How does elevated measurement noise affect logical memory performance?';
  }
  if (b.dataset.preset === 'mismatch') {
    s.decoder = 'mismatched';
    s.title = 'Decoder noise-model mismatch';
    s.question = 'What changes when the decoder assumes measurement noise p while the circuit uses 3p?';
  }
  fillPlan(s);
}));
on('#plan-form', 'submit', async e => {
  e.preventDefault();
  $('#submit-run').disabled = true;
  $('#plan-error').hidden = true;
  try {
    const spec = readPlan(),
      r = await post('/runs', spec);
    $('#plan-dialog').close();
    await loadRun(r.id);
    tab('results');
    notify('Investigation queued. Collecting real simulation evidence.');
  } catch (err) {
    $('#plan-error').hidden = false;
    $('#plan-error').textContent = err.message;
  } finally {
    $('#submit-run').disabled = false;
  }
});
on('#cancel-run', 'click', async () => {
  if (state.run) {
    await post('/runs/' + state.run.id + '/cancel', {});
    notify('Cancellation requested. Current batch will finish safely.');
  }
});
on('#export-run', 'click', () => {
  if (state.run) window.location.href = '/api/runs/' + state.run.id + '/export';
});
on('#method-button', 'click', () => $('#method-dialog').showModal());
on('#close-method', 'click', () => $('#method-dialog').close());
$$('dialog').forEach(d => d.addEventListener('click', e => {
  if (e.target === d) {
    const r = d.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) d.close();
  }
}));
on('#key-form', 'submit', async e => {
  e.preventDefault();
  const key = $('#api-key').value.trim();
  if (!key) throw Error('Enter an API key first.');
  await post('/settings', {
    api_key: key
  });
  $('#api-key').value = '';
  state.health = await api('/health');
  renderHealth();
  notify('Key configured for this server session.');
});
on('#disconnect-key', 'click', async () => {
  await post('/settings', {
    api_key: ''
  });
  state.health = await api('/health');
  renderHealth();
  notify('Gemini disconnected.');
});
$$('[data-prompt]').forEach(b => b.addEventListener('click', () => {
  $('#chat-input').value = b.dataset.prompt;
  $('#chat-input').focus();
}));

function message(text, type = 'assistant-message') {
  const el = document.createElement('div');
  el.className = 'chat-message ' + type;
  const label = document.createElement('span');
  label.className = 'message-label';
  label.textContent = type === 'user' ? 'YOU' : 'QEC LAB';
  el.append(label, document.createTextNode(text));
  $('#chat-messages').append(el);
  el.scrollIntoView({
    block: 'nearest'
  });
  return el;
}

function showAnswer(r) {
  if (r.trace.length) {
    const t = document.createElement('div');
    t.className = 'tool-trace';
    t.textContent = r.trace.map(v => '✓ ' + v).join('\n');
    $('#chat-messages').append(t);
  }
  const response = message(r.answer);
  if (r.proposal) {
    const p = document.createElement('div');
    p.className = 'proposal-card';
    p.innerHTML = '<h3>' + esc(r.proposal.title) + '</h3><p>' + r.proposal.distances.length * r.proposal.probabilities.length + ' configurations · ' + fmt(r.proposal.shots) + ' shots per point</p>';
    const b = document.createElement('button');
    b.className = 'button';
    b.textContent = 'Review experiment plan ↗';
    b.onclick = () => openPlan(r.proposal);
    p.append(b);
    response.append(p);
  }
}
async function loadChat() {
  const scope = state.run?.id || 'draft',
    items = await api('/messages?scope=' + encodeURIComponent(scope));
  if (scope !== (state.run?.id || 'draft')) return;
  $$('#chat-messages > .chat-message, #chat-messages > .tool-trace').forEach(el => el.remove());
  $('.assistant-intro').hidden = items.length > 0;
  for (const item of items) {
    message(item.message, 'user');
    showAnswer(item);
  }
}
on('#chat-form', 'submit', async e => {
  e.preventDefault();
  if (state.chatBusy) return;
  const text = $('#chat-input').value.trim();
  if (!text) return;
  if (!state.health?.gemini_connected) {
    notify('Connect your Gemini key in Settings to use the assistant.');
    view('settings');
    return;
  }
  state.chatBusy = true;
  $('#send-chat').disabled = true;
  $('#chat-input').value = '';
  $('.assistant-intro').hidden = true;
  const scope = state.run?.id || null;
  message(text, 'user');
  const pending = message('Inspecting context and choosing tools…');
  try {
    const r = await post('/assistant', {
      message: text,
      spec: state.spec,
      run_id: scope
    });
    pending.remove();
    if (scope !== (state.run?.id || null)) {
      notify('Assistant response saved to the original investigation.');
      return;
    }
    showAnswer(r);
  } catch (err) {
    pending.remove();
    if (scope === (state.run?.id || null)) message(err.message, 'error');
    else notify(err.message);
  } finally {
    state.chatBusy = false;
    $('#send-chat').disabled = false;
  }
});
on('#chat-input', 'keydown', e => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    $('#chat-form').requestSubmit();
  }
});
async function boot() {
  renderRun();
  try {
    state.health = await api('/health');
    renderHealth();
    await refreshRuns();
    const draft = await api('/draft');
    if (draft) state.spec = draft;
    const selected = location.hash.startsWith('#run=') ? location.hash.slice(5) : null;
    if (selected && state.runs.some(r => r.id === selected)) await loadRun(selected);
    else if (location.hash !== '#draft' && state.runs.length) await loadRun(state.runs[0].id);
    else {
      renderRun();
      await loadChat();
    }
  } catch (err) {
    $('#connection').innerHTML = '<i></i>Engine unavailable';
    $('#connection').classList.add('offline');
    $('#engine-label').textContent = 'Start the application server';
    notify(err.message);
  }
}
let chartWidth = 0;
new ResizeObserver(entries => {
  const width = entries[0].contentRect.width;
  if (width && width !== chartWidth) {
    chartWidth = width;
    renderChart();
  }
}).observe($('#chart'));
boot();
if (document.modelContext?.registerTool) {
  const lifecycle = new AbortController();
  window.addEventListener('pagehide', () => lifecycle.abort(), {
    once: true
  });
  const tools = [{
    name: 'get_qec_investigation',
    description: 'Read the selected QEC investigation and its measured point summaries.',
    inputSchema: {
      type: 'object',
      properties: {},
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true
    },
    execute: async () => ({
      id: state.run?.id || null,
      spec: state.spec,
      status: state.run?.status || 'draft',
      points: state.run?.points.map(({
        failure,
        batches,
        ...p
      }) => p) || []
    })
  }, {
    name: 'stage_qec_preset',
    description: 'Open a preset experiment plan for review. Does not execute or save an experiment.',
    inputSchema: {
      type: 'object',
      properties: {
        preset: {
          type: 'string',
          enum: ['baseline', 'noise', 'mismatch']
        }
      },
      required: ['preset'],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: false
    },
    execute: async input => {
      if (!input || !['baseline', 'noise', 'mismatch'].includes(input.preset)) throw Error('Invalid preset');
      openPlan();
      $('[data-preset="' + input.preset + '"]').click();
      return {
        staged: true,
        execution: 'Requires Run investigation'
      };
    }
  }];
  tools.forEach(tool => Promise.resolve(document.modelContext.registerTool(tool, {
    signal: lifecycle.signal
  })).catch(() => {}));
}
