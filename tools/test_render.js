// Drives lib/render.js headlessly over the real specs.
//
//   npm install --no-save jsdom        # once, in the repository root
//   node tools/test_render.js
//
// 1. every listing runs to a submitted payload for a spread of participant ids;
// 2. show_if, pipe and page behave as the rebuilt specs rely on (fkrsd, 6cxdn, kf4e6).
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { JSDOM } = require('jsdom');

const SITE = path.resolve(__dirname, '..');
const RENDER = fs.readFileSync(path.join(SITE, 'lib/render.js'), 'utf8');

function boot(listing, pid) {
  const dom = new JSDOM('<div id="app"></div>', {
    url: `https://x.test/?PROLIFIC_PID=${pid}`, runScripts: 'outside-only' });
  const w = dom.window;
  w.TextEncoder = TextEncoder;
  const box = { payload: null };
  w.proliferate = { submit: p => { box.payload = p; } };
  w.eval(RENDER);
  w.runSpec(JSON.parse(fs.readFileSync(path.join(SITE, listing, 'spec.json'))));
  const d = w.document;
  return {
    d, box,
    text: () => d.querySelector('.card').textContent,
    // answer everything on screen; `values` overrides by variable-name
    answer(values = {}) {
      for (const el of d.querySelectorAll('input[type=range]')) {
        const v = el.id.replace(/^w_/, '');
        el.value = values[v] !== undefined ? values[v] : 40;
        el.dispatchEvent(new w.Event('input'));
      }
      for (const el of d.querySelectorAll('input.freetext, textarea, input.idea-in')) {
        const v = el.id.replace(/^w_/, '');
        el.value = values[v] !== undefined ? values[v] : `my ${v}`;
      }
      const radios = {};
      for (const el of d.querySelectorAll('input[type=radio], input[type=checkbox]')) {
        (radios[el.name] = radios[el.name] || []).push(el);
      }
      for (const [nm, els] of Object.entries(radios)) {
        const want = values[nm.replace(/^w_/, '')];
        (els.find(e => e.value === String(want)) || els[0]).checked = true;
      }
    },
    next() { d.getElementById('next').click(); },
    back() { d.getElementById('back').click(); },
    onScreen: () => [...d.querySelectorAll('input, textarea')]
      .map(e => (e.id || e.name).replace(/^w_/, '')),
  };
}

function finish(s, values = {}, max = 2000) {
  for (let k = 0; k < max && !s.box.payload; k++) { s.answer(values); s.next(); }
  assert(s.box.payload, 'never submitted');
  return s.box.payload.trials.map(t => t.variable_name);
}

function runTo(s, pred, values, max = 400) {
  for (let k = 0; k < max; k++) {
    if (pred()) return true;
    s.answer(values);
    s.next();
  }
  return false;
}

// ---------- 1. every listing completes, every arm reachable
for (const listing of fs.readdirSync(SITE).sort()) {
  if (!fs.existsSync(path.join(SITE, listing, 'spec.json'))) continue;
  const spec = JSON.parse(fs.readFileSync(path.join(SITE, listing, 'spec.json')));
  const arms = new Set();
  const n = spec.arms ? Math.max(12, 4 * spec.arms) : 4;
  for (let k = 0; k < n; k++) {
    const s = boot(listing, `pid${k}`);
    const got = finish(s);
    assert(got.length > 0, `${listing}: empty payload`);
    arms.add(s.box.payload.subject_information.arm);
  }
  if (spec.arms) assert.strictEqual(arms.size, spec.arms, `${listing}: arms not all reached`);
  console.log(`ok  ${listing}: ${n} participants, ${spec.arms || 1} arm(s) reached`);
}

// ---------- 2. fkrsd: entry fields, piping, the >50 gate
{
  const s = boot('fkrsd', 't1');
  s.next(); // consent
  const vals = { drop_habit_good_1: 80, drop_habit_bad_3: 51 };
  assert(runTo(s, () => s.onScreen().includes('habit_env_good_1'), vals), 'entry page');
  assert.strictEqual(s.onScreen().filter(n => n.startsWith('habit_')).length, 4);
  s.answer({ habit_env_good_1: 'cycling to work' });
  s.next();
  assert(runTo(s, () => s.text().includes('How strong is cycling to work'), vals), 'piped');
  const got = finish(s, vals);
  const returns = got.filter(n => n.startsWith('return_home_')).sort();
  assert.strictEqual(JSON.stringify(returns),
    JSON.stringify(['return_home_bad_3', 'return_home_good_1']));
  console.log('ok  fkrsd: typed habits piped into later items; only returns rated >50 shown');
}
{
  // going back and lowering the gate removes the answer it had unlocked
  const s = boot('fkrsd', 't2');
  s.next();
  const vals = { drop_habit_good_1: 80, drop_habit_bad_4: 80 };
  assert(runTo(s, () => s.onScreen().includes('return_home_good_1'), vals), 'reach return');
  s.answer({ return_home_good_1: 90 });
  s.next();
  assert(s.onScreen().includes('return_home_bad_4'));
  for (let k = 0; k < 40 && !s.onScreen().includes('drop_habit_good_1'); k++) s.back();
  assert(s.onScreen().includes('drop_habit_good_1'), 'back to gate');
  const low = { drop_habit_good_1: 10, drop_habit_bad_4: 80 };
  for (let k = 0; k < 200 && !s.box.payload; k++) {
    assert(!s.onScreen().includes('return_home_good_1'), 'gated-out item shown');
    s.answer(low);
    s.next();
  }
  const got = s.box.payload.trials.map(t => t.variable_name);
  assert(!got.includes('return_home_good_1'), 'stale gated answer submitted');
  assert(got.includes('return_home_bad_4'));
  console.log('ok  fkrsd: an answer hidden by a changed gate is not submitted');
}

// ---------- 6cxdn: the status answer takes the reconstruction's branch
for (const [status, want, not] of [['Yes', 'PRQC.1', 'liking.1'], ['No', 'liking.1', 'PRQC.1']]) {
  const s = boot('6cxdn', 'c' + status);
  s.next();
  const got = finish(s, { relationship_status: status });
  assert(got.includes(want) && !got.includes(not), `6cxdn ${status}`);
  console.log(`ok  6cxdn: "${status}" shows ${want}, hides ${not}`);
}

// ---------- kf4e6: vignette and rating on one page
{
  const s = boot('kf4e6', 'k1');
  s.next(); s.next(); // consent, directions
  assert.strictEqual(s.d.querySelectorAll('.stim').length, 1);
  assert.strictEqual(s.d.querySelectorAll('.qtext').length, 1);
  console.log('ok  kf4e6: vignette and its rating share one page');
}
console.log('all passed');
