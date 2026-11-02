// Drives lib/render.js headlessly over the real specs.
//
//   npm install --no-save jsdom        # once, in the repository root
//   node tools/test_render.js
//
// 1. every listing runs to a submitted payload for a spread of participant ids;
// 2. show_if, pipe and page behave as the rebuilt specs rely on (fkrsd, 6cxdn, kf4e6,
//    fxp7g, kfrux, kxcwm), and every answer carries rt_ms.
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
  assert(runTo(s, () => s.text().includes('How strong are those habits?')
                && s.text().includes('cycling to work'), vals), 'piped');
  assert(!s.text().includes('The first habit you listed'), 'phrase left in place');
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

// ---------- fxp7g: manipulated_goal draws either framing; ratings are one matrix page
{
  const seen = new Set();
  for (let k = 0; k < 120 && seen.size < 2; k++) {
    const s = boot('fxp7g', `g${k}`);
    s.next();
    for (let j = 0; j < 4; j++) {
      if (s.text().includes('credible and trustworthy news. ')) seen.add('credible');
      if (s.text().includes('entertaining and fun news. ')) seen.add('entertaining');
      s.answer(); s.next();
    }
  }
  assert.strictEqual(seen.size, 2, `fxp7g: framings drawn ${[...seen]}`);
  const s = boot('fxp7g', 'm1');
  s.next();
  assert(runTo(s, () => s.d.querySelectorAll('.qtext').length === 8), 'matrix page');
  console.log('ok  fxp7g: both goal framings are drawn; eight headlines share a page');
}

// ---------- kfrux: price is a number box and comes back as a number
{
  const s = boot('kfrux', 'p1');
  s.next();
  assert(runTo(s, () => s.d.querySelector('input.num-in')), 'price box');
  const got = finish(s, { price: '25' });
  void got;
  const t = s.box.payload.trials.find(x => x.variable_name === 'price');
  assert.strictEqual(t.answer, 25);
  assert(s.box.payload.trials.every(x => typeof x.rt_ms === 'number'), 'rt_ms missing');
  console.log('ok  kfrux: price submitted as a number; every answer has rt_ms');
}

// ---------- kxcwm: a CAQ checklist appears only for a domain the participant picked
{
  const s = boot('kxcwm', 'q1');
  const got = finish(s, { idiff_caq_domains: 'Music, including singing' });
  assert(got.includes('caq_music_achievements') && !got.includes('caq_dance_achievements'),
         'kxcwm CAQ gate');
  console.log('ok  kxcwm: CAQ achievements gated on the domains picked');
}
// ---------- ba65f_B: 5 high + 5 low per person, levels not shown in a fixed pattern
{
  const patterns = new Set();
  const firstHigh = [];
  for (let k = 0; k < 200; k++) {
    const s = boot('ba65f_B', `b${k}`);
    const sits = [];
    for (const v of finish(s)) {
      const m = v.match(/^([a-z]+)_([hl])_/);
      if (m && (!sits.length || sits[sits.length - 1][0] !== m[1])) sits.push([m[1], m[2]]);
    }
    const seq = sits.map(x => x[1]).join('');
    assert.strictEqual(sits.length, 10, `ba65f_B: ${sits.length} situations`);
    assert.strictEqual(seq.split('h').length - 1, 5, `ba65f_B: ${seq} is not 5 high + 5 low`);
    patterns.add(seq);
    firstHigh.push(seq[0] === 'h');
  }
  const share = firstHigh.filter(Boolean).length / firstHigh.length;
  assert(patterns.size > 50, `ba65f_B: only ${patterns.size} level orders`);
  assert(share > 0.35 && share < 0.65, `ba65f_B: first situation high-cost ${share}`);
  console.log(`ok  ba65f_B: 5+5 levels, ${patterns.size} distinct level orders in 200`);
}
console.log('all passed');
