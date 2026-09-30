// Drives lib/render.js headlessly over the real specs.
//
//   npm install --no-save jsdom        # once, in the repository root
//   node tools/test_render.js
//
// 1. every listing runs to a submitted payload for a spread of participant ids;
// 2. show_if, pipe and page behave as the rebuilt specs rely on (fkrsd, 6cxdn, kf4e6);
// 3. each conversion fix holds: site items, 6cxdn branch order and initials, fkrsd bad
//    non-habit items dropped, cse5r follow-ups, fxp7g framings, 6fjdr matrix, kxcwm lock, ba65f_B order.
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

// ---------- every listing closes with the site's attention check and demographics
for (const listing of fs.readdirSync(SITE).sort()) {
  if (!fs.existsSync(path.join(SITE, listing, 'spec.json'))) continue;
  const got = finish(boot(listing, 'site1'));
  assert(got.includes('site_attention_check'), `${listing}: no attention check`);
  assert(got.includes('participant-info.age') && got.includes('participant-info.gender'),
    `${listing}: no demographics`);
}
console.log('ok  all listings: attention check and demographics submitted');

// ---------- 6cxdn: status asked first, initials piped, singles skip partner items
{
  const s = boot('6cxdn', 'c1');
  s.next(); // consent
  assert.deepStrictEqual([...new Set(s.onScreen())], ['relationship_status'],
    'status is the first question');
  s.answer({ relationship_status: 'No' }); s.next();
  assert(s.onScreen().includes('partner_initials'), 'initials asked second');
  s.answer({ partner_initials: 'J.K.' }); s.next();
  assert(runTo(s, () => s.text().includes('How physically attractive is J.K.?'),
    { relationship_status: 'No' }), 'initials piped');
  const got = finish(s, { relationship_status: 'No' });
  for (const n of ['PRQC.1', 'GMSEX.1', 'SexDes.1']) assert(!got.includes(n), `single saw ${n}`);
  assert.strictEqual(got.filter(n => n === 'PRQC.1').length, 0);
  console.log('ok  6cxdn: status first, initials piped, singles never see partner items');
}
{
  const s = boot('6cxdn', 'c2');
  s.next(); s.answer({ relationship_status: 'Yes' }); s.next();
  s.answer({ partner_initials: '' }); s.next(); s.next(); // blank: confirm the skip
  assert(runTo(s, () => s.text().includes('How physically attractive is <initials>?'),
    { relationship_status: 'Yes', partner_initials: '' }), 'blank slot stays visible');
  const got = finish(s, { relationship_status: 'Yes', partner_initials: '' });
  assert.strictEqual(got.filter(n => n === 'PRQC.1').length, 1, 'PRQC.1 asked once');
  console.log('ok  6cxdn: a blank slot shows its label instead of vanishing; PRQC.1 once');
}

// ---------- fkrsd: keep_newh_* is gated; items naming an uncollected slot are dropped
{
  const s = boot('fkrsd', 't3');
  s.next();
  const vals = { good_habit_start_2: 90 }; // slider ids sanitise spaces
  const got = finish(s, vals);
  assert.deepStrictEqual([...got.filter(n => n.startsWith('keep_newh_'))], ['keep_newh_good_2']);
  assert(!got.some(n => n.startsWith('bad habit_start_') || n.startsWith('keep_newh_bad_')),
    'item naming the never-collected bad non-habit slot reached a participant');
  console.log('ok  fkrsd: keep_newh_* only after >50; uncollected bad non-habit items dropped');
}

// ---------- cse5r: initiative follow-ups only after "Yes"
for (const [ans, want] of [['Yes', true], ['No', false]]) {
  const got = finish(boot('cse5r', 'i' + ans), { initiative: ans });
  assert.strictEqual(got.includes('org_goals') && got.includes('endorse_personally'), want);
}
console.log('ok  cse5r: org_goals/goals/endorse_* follow a "Yes" to initiative only');

// ---------- fxp7g: both framings of the manipulated goal are fielded
{
  const seen = new Set();
  for (let k = 0; k < 80 && seen.size < 2; k++) {
    const s = boot('fxp7g', 'g' + k);
    for (let p = 0; p < 4; p++) {
      s.next();
      const t = s.text();
      if (t.includes('find credible')) seen.add('credibility');
      if (t.includes('find entertaining')) seen.add('enjoyment');
    }
  }
  assert.strictEqual(seen.size, 2, 'enjoyment framing never shown');
  console.log('ok  fxp7g: credibility and enjoyment framings both shown');
}

// ---------- 6fjdr: the recorded 14-row impact matrix is one screen
{
  const s = boot('6fjdr', 'm1');
  s.next();
  assert(runTo(s, () => s.onScreen().includes('Impact_buyless')), 'impact page');
  assert.strictEqual(new Set(s.onScreen().filter(n => n.startsWith('Impact_'))).size, 14);
  console.log('ok  6fjdr: impact matrix on one page');
}

// ---------- kxcwm: timed idea pages cannot be left early
{
  const s = boot('kxcwm', 'x1');
  s.next();
  assert(runTo(s, () => !!s.d.getElementById('ti-clock')), 'timed page');
  assert(s.d.getElementById('next').hidden, 'early exit offered');
  const back = s.d.getElementById('back');
  assert(!back || back.hidden, 'back offered on a locked timed page');
  console.log('ok  kxcwm: timed pages run their full time');
}

// ---------- ba65f_B: level order is not a fixed alternation
{
  const firsts = new Set();
  for (let k = 0; k < 16; k++) {
    const got = finish(boot('ba65f_B', 'b' + k));
    const lv = got.map(n => (n.match(/_([hl])_/) || [])[1]).filter(Boolean);
    firsts.add(lv.join(''));
  }
  assert(firsts.size > 2, 'every participant got the same level order');
  console.log(`ok  ba65f_B: ${firsts.size} distinct high/low orders over 16 participants`);
}
console.log('all passed');
