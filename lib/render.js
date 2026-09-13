/* Page-stack renderer: spec.json -> one page at a time, with Back -> POST /data
 *
 * Entry point is runSpec(spec), same as before, and the spec format and the stored
 * payload shape are unchanged — so ingest.py, replay_check.py and score.py are
 * untouched by this file.
 *
 * Why not jsPsych's timeline: it is forward-only. There is no supported way to step
 * back a trial, and emulating it with loop_function nests badly and loses answers.
 * The four widgets the archive needs (0-100 slider, <=7-point Likert grid, single/
 * multi choice, free text) are small enough to render directly, which also lets us
 * guarantee the two things that matter scientifically: a slider with NO default
 * position, and answers that survive navigating back and forth.
 *
 * Spec shape:
 *   { "study": "...", "completion_url": "...", "screenout_url": "...",
 *     "arms": 2, "consent": "<p>...</p>",
 *     "blocks": [ block, ... ]            // or "arm_blocks": [ [block...], ... ]
 *   }
 * where a block is one of
 *   {"type":"stimuli","variable-name":..,"content":"..."}
 *   {"type":"question","variable-name":..,"question":"..","response-constraints":{..},
 *    "qualify_values":[..],"disqualify_values":[..]}
 *   {"type":"timed-ideas","variable-name":..,"question":"..","n_fields":15,
 *    "duration_ms":120000}
 *   {"type":"group","shuffle":true,"pick":N,"items":[block...]}
 *   {"type":"interleave","items":[group,...]}   // expand each, then shuffle the runs
 */

/* ---------- deterministic per-participant randomness ----------
 * FNV-1a 32-bit then murmur3's fmix32. Deliberately NOT crypto.subtle: that exists
 * only in a secure context, so on a plain-HTTP host it is undefined and arm
 * assignment would break with no obvious symptom. Uniform and reproducible is all
 * this needs to be; replication/pidhash.py reproduces it exactly for the ingest
 * audit. */
function pidHash(str) {
  const bytes = new TextEncoder().encode(str);
  let h = 0x811c9dc5;
  for (let i = 0; i < bytes.length; i++) {
    h ^= bytes[i];
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  h ^= h >>> 16;
  h = Math.imul(h, 0x85ebca6b) >>> 0;
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35) >>> 0;
  h ^= h >>> 16;
  return h >>> 0;
}

function seededRng(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffled(arr, rng) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ---------- spec -> flat page list ---------- */
function selectFrom(group, rng) {
  let items = group.shuffle ? shuffled(group.items, rng) : group.items.slice();
  if (group.pick) items = items.slice(0, group.pick);
  return items;
}

// Returns an array of "runs"; a run is an array of pages that must stay together
// and in order (a stimulus followed by its question).
function expandRuns(blocks, rng) {
  const runs = [];
  for (const b of blocks) {
    if (b.type === 'group') {
      // A group with neither shuffle nor pick is a SEQUENCE that must stay
      // together — a vignette and its question. Returning its children as
      // separate runs let `interleave` shuffle a stimulus away from the question
      // it belongs to, so a participant read one article and answered about
      // another. Collapse it into one run instead.
      if (!b.shuffle && !b.pick) {
        const one = [];
        for (const child of b.items) {
          for (const r of expandRuns([child], rng)) one.push(...r);
        }
        runs.push(one);
        continue;
      }
      for (const child of selectFrom(b, rng)) runs.push(...expandRuns([child], rng));
    } else if (b.type === 'balanced') {
      // One variant per cell, with the variant LEVELS balanced across cells. The
      // archive's design fixes this split (every Group B participant saw exactly 5
      // high-cost and 5 low-cost actions); drawing a level per cell independently
      // would give a binomial spread instead.
      const cells = shuffled(b.items, rng);
      const levels = [...new Set(
        b.items.flatMap(c => c.items.map(v => v.level)).filter(x => x != null))].sort();
      cells.forEach((cell, k) => {
        const want = levels.length ? levels[k % levels.length] : null;
        const chosen = cell.items.find(v => v.level === want) || cell.items[0];
        runs.push(...expandRuns([chosen], rng));
      });
    } else if (b.type === 'interleave') {
      const inner = [];
      for (const child of b.items) {
        for (const picked of selectFrom(child, rng)) {
          inner.push(...expandRuns([picked], rng));
        }
      }
      runs.push(...shuffled(inner, rng));
    } else {
      runs.push([b]);
    }
  }
  return runs;
}

function flatten(blocks, rng) {
  // A group with shuffle but no pick still needs its runs kept intact, which
  // expandRuns already guarantees; concatenating here preserves that order.
  return expandRuns(blocks, rng).flat();
}

/* ---------- widgets ----------
 * Each returns {html, read, fill, focus}. `read` returns undefined when unanswered
 * so required-field enforcement is uniform across widget types.
 */
function widget(item) {
  const rc = item['response-constraints'] || {};
  const name = item['variable-name'];
  const id = 'w_' + name.replace(/[^A-Za-z0-9_]/g, '_');

  if (rc.type === 'scalar') {
    const lo = rc['scale-min'], hi = rc['scale-max'];
    const loD = rc['scale-min-desc'] === undefined ? lo : rc['scale-min-desc'];
    const hiD = rc['scale-max-desc'] === undefined ? hi : rc['scale-max-desc'];
    if ((hi - lo) <= 6) {
      // discrete radio grid, as the archive's <=7-point Likert items were shown
      let cells = '';
      for (let v = lo; v <= hi; v++) {
        const lab = v === lo ? `<span class="anch">${esc(loD)}</span>`
          : v === hi ? `<span class="anch">${esc(hiD)}</span>` : '';
        cells += `<label class="lik"><input type="radio" name="${id}" value="${v}">` +
          `<span class="num">${v}</span>${lab}</label>`;
      }
      return {
        html: `<div class="likgrid">${cells}</div>`,
        read: () => {
          const el = document.querySelector(`input[name="${id}"]:checked`);
          return el ? Number(el.value) : undefined;
        },
        fill: v => {
          const el = document.querySelector(`input[name="${id}"][value="${v}"]`);
          if (el) el.checked = true;
        },
      };
    }
    // wide scale -> slider with NO default handle position
    return {
      html:
        `<div class="sliderwrap">` +
        `<input type="range" id="${id}" min="${lo}" max="${hi}" ` +
        `step="${rc.step || 1}" value="${Math.round((lo + hi) / 2)}" ` +
        `class="slider unset">` +
        `<div class="anchrow"><span>${esc(loD)}</span><span>${esc(hiD)}</span></div>` +
        `<div class="sliderval" id="${id}_v">move the slider to answer</div></div>`,
      read: () => {
        const el = document.getElementById(id);
        return el && !el.classList.contains('unset') ? Number(el.value) : undefined;
      },
      fill: v => {
        const el = document.getElementById(id);
        if (!el) return;
        el.value = v;
        el.classList.remove('unset');
        const out = document.getElementById(id + '_v');
        if (out) out.textContent = String(v);
      },
      wire: () => {
        const el = document.getElementById(id);
        const out = document.getElementById(id + '_v');
        if (!el) return;
        const upd = () => {
          el.classList.remove('unset');
          if (out) out.textContent = el.value;
        };
        el.addEventListener('input', upd);
        el.addEventListener('change', upd);
      },
    };
  }

  if (rc.type === 'mcq') {
    const opts = rc.options || [];
    const multi = (rc['max-choices'] || 1) > 1;
    const type = multi ? 'checkbox' : 'radio';
    const html = opts.map((o, i) =>
      `<label class="opt"><input type="${type}" name="${id}" value="${esc(o)}">` +
      `<span>${esc(o)}</span></label>`).join('');
    return {
      html: `<div class="opts">${html}</div>`,
      read: () => {
        const sel = [...document.querySelectorAll(`input[name="${id}"]:checked`)]
          .map(e => e.value);
        if (!sel.length) return undefined;
        return multi ? sel : sel[0];
      },
      fill: v => {
        const vals = Array.isArray(v) ? v : [v];
        for (const el of document.querySelectorAll(`input[name="${id}"]`)) {
          if (vals.includes(el.value)) el.checked = true;
        }
      },
    };
  }

  if (rc.type === 'free-response') {
    const limit = rc['response-limit'];
    return {
      html: `<textarea id="${id}" rows="5" class="freetext"${
        limit ? ` maxlength="${limit}"` : ''}></textarea>`,
      // free text is optional: the archive contains blank responses
      read: () => {
        const el = document.getElementById(id);
        return el ? el.value : undefined;
      },
      optional: true,
      fill: v => { const el = document.getElementById(id); if (el) el.value = v; },
      focus: () => { const el = document.getElementById(id); if (el) el.focus(); },
    };
  }

  throw new Error(`unsupported response type ${JSON.stringify(rc.type)} on ${name}`);
}

/* ---------- the runner ---------- */
async function runSpec(spec) {
  const url = new URLSearchParams(location.search);
  // proliferate is the production entry point: it creates a participant record and
  // redirects here as ?participant_id=<uuid>&experiment_id=<uuid>. It does NOT pass
  // the Prolific ID — proliferate keeps that and hands it back only in the separate
  // <experiment>-workerids.csv. PROLIFIC_PID is the fallback for local review and
  // for replay_check.py, which drive the app directly without proliferate.
  const pid = url.get('participant_id') || url.get('PROLIFIC_PID') || '';
  const root = document.getElementById('app') || document.body;
  if (!pid) {
    root.innerHTML = '<div class="card"><p>This link is missing its Prolific ID. ' +
      'Please return to Prolific and use the study link there.</p></div>';
    return;
  }

  const seed = pidHash(pid);
  const rng = seededRng(seed);
  const arm = spec.arms ? seed % spec.arms : null;
  const blocks = spec.arm_blocks ? spec.arm_blocks[arm] : spec.blocks;

  const pages = flatten(blocks, rng);
  if (spec.consent) {
    pages.unshift({ type: 'stimuli', 'variable-name': '__consent',
                    content: spec.consent, consent: true });
  }

  const answers = {};          // variable-name -> {answer, condition}
  const order = [];            // presentation order, first visit only
  const started = performance.now();
  let i = 0;
  let screenedOut = null;
  let timedDone = {};          // a timed page cannot be re-entered
  let current = null;          // {item, w} for the page on screen
  let skipArmed = null;        // variable-name whose skip has been offered once

  function commit() {
    if (!current || !current.w) return true;
    const { item, w } = current;
    const v = w.read();
    const blank = v === undefined || v === null || (Array.isArray(v) && !v.length);
    // Participants have the right to decline any question (IRB-88942 comment 7), so a
    // blank answer is never ultimately refused. One soft confirmation keeps accidental
    // skips down without making the item mandatory. Do not restore a hard block.
    if (blank && !w.optional && skipArmed !== item['variable-name']) {
      skipArmed = item['variable-name'];
      const err = document.getElementById('err');
      if (err) err.textContent = 'You may leave this question blank if you would '
        + 'rather not answer \u2014 press Continue again to skip it.';
      return false;
    }
    skipArmed = null;
    answers[item['variable-name']] = { answer: v, condition: item.condition || null };
    const bad = item.disqualify_values || [];
    const keep = item.qualify_values || [];
    if ((bad.length && bad.includes(v)) || (keep.length && !keep.includes(v))) {
      screenedOut = item['variable-name'];
    } else if (screenedOut === item['variable-name']) {
      screenedOut = null;      // they went back and changed the answer
    }
    return true;
  }

  function render() {
    if (screenedOut !== null || i >= pages.length) return finish();
    const item = pages[i];
    if (order.indexOf(item['variable-name']) === -1) {
      order.push(item['variable-name']);
    }
    // Back is offered on every page except the first, and is not offered INTO a
    // completed timed task — re-entering would hand out a second two minutes.
    const prev = pages[i - 1];
    const canBack = i > 0 && !(prev && prev.type === 'timed-ideas'
                               && timedDone[prev['variable-name']]);
    const pct = Math.round(100 * i / pages.length);

    if (item.type === 'timed-ideas') return renderTimed(item, canBack, pct);

    let body, w = null;
    if (item.type === 'stimuli') {
      body = `<div class="stim">${item.content}</div>`;
    } else {
      w = widget(item);
      body = `<div class="qtext">${item.question}</div>${w.html}`;
    }
    root.innerHTML =
      `<div class="bar"><div class="fill" style="width:${pct}%"></div></div>` +
      `<div class="card">${body}<p class="err" id="err"></p>` +
      `<div class="nav">` +
      (canBack ? `<button id="back" class="ghost">&larr; Back</button>`
               : `<span></span>`) +
      `<button id="next" class="primary">${
        item.consent ? 'I consent, begin the study'
          : i === pages.length - 1 ? 'Finish' : 'Continue'}</button>` +
      `</div></div>`;
    current = { item, w };
    if (w) {
      if (w.wire) w.wire();
      const prevAns = answers[item['variable-name']];
      if (prevAns && prevAns.answer !== undefined && w.fill) w.fill(prevAns.answer);
      if (w.focus) w.focus();
    }
    const back = document.getElementById('back');
    if (back) back.onclick = () => { current = null; i--; render(); };
    document.getElementById('next').onclick = () => {
      if (!commit()) return;
      current = null;
      i++;
      render();
    };
  }

  function renderTimed(item, canBack, pct) {
    const n = item.n_fields || 15;
    const ms = item.duration_ms || 120000;
    const base = item['variable-name'];
    let boxes = '';
    for (let k = 1; k <= n; k++) {
      boxes += `<div class="idea-row"><span class="idea-n">${k}.</span>` +
        `<input type="text" id="${esc(base)}_${k}" class="idea-in" ` +
        `autocomplete="off"></div>`;
    }
    root.innerHTML =
      `<div class="bar"><div class="fill" style="width:${pct}%"></div></div>` +
      `<div class="card"><div class="qtext">${item.question}</div>` +
      `<div class="timer">Time remaining: <span id="ti-clock">--:--</span></div>` +
      `<div class="idea-grid">${boxes}</div>` +
      `<div class="nav">` +
      (canBack ? `<button id="back" class="ghost">&larr; Back</button>`
               : `<span></span>`) +
      `<button id="next" class="primary">I'm done</button></div></div>`;
    current = null;

    const clock = document.getElementById('ti-clock');
    const end = performance.now() + ms;
    let iv = null;
    const done = () => {
      if (iv) clearInterval(iv);
      iv = null;
      let filled = 0;
      for (let k = 1; k <= n; k++) {
        const el = document.getElementById(`${base}_${k}`);
        const v = el ? el.value.trim() : '';
        if (v) {
          filled++;
          answers[`${base}_${k}`] = { answer: v, condition: item.condition || null };
        }
      }
      answers[`${base}__n_submitted`] =
        { answer: filled, condition: item.condition || null };
      timedDone[base] = true;
      i++;
      render();
    };
    const tick = () => {
      const left = Math.max(0, Math.round((end - performance.now()) / 1000));
      if (clock) {
        clock.textContent = Math.floor(left / 60) + ':' +
          String(left % 60).padStart(2, '0');
        if (left <= 15) clock.classList.add('low');
      }
      if (left <= 0) done();
    };
    iv = setInterval(tick, 250);
    tick();
    const first = document.getElementById(`${base}_1`);
    if (first) first.focus();
    const back = document.getElementById('back');
    if (back) back.onclick = () => { if (iv) clearInterval(iv); i--; render(); };
    document.getElementById('next').onclick = done;
  }

  async function finish() {
    // #thanks is where proliferate posts its own upload-status messages.
    root.innerHTML = '<div class="card"><p id="thanks">Saving your '
      + 'responses&hellip;</p></div>';
    const payload = {
      study: spec.study,
      prolific_pid: pid,
      participant_id: url.get('participant_id'),
      experiment_id: url.get('experiment_id'),
      study_id: url.get('STUDY_ID'),
      session_id: url.get('SESSION_ID'),
      arm: arm,
      item_order: order,
      screened_out: screenedOut,
      duration_seconds: Math.round((performance.now() - started) / 1000),
      answers: answers,
      renderer: 'page-stack/1.0',
    };
    // In production the sink is proliferate. proliferate.submit takes CALLBACKS, not
    // a promise: called with no callbacks it stores the data, redirects to the
    // Prolific completion URL configured on the proliferate side, and shows its own
    // failure message. Do not await it — an awaited call resolves immediately and
    // would report success even when the upload failed.
    if (window.proliferate && typeof window.proliferate.submit === 'function') {
      window.proliferate.submit(payload);
      return;
    }
    let ok = false;
    // No proliferate library: fall back to the local serve.py endpoint, which is
    // what replay_check.py and local review use.
    for (let attempt = 0; attempt < 3 && !ok; attempt++) {
      try {
        const r = await fetch('/data', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        ok = r.ok;
      } catch (e) { /* retry */ }
      if (!ok) await new Promise(res => setTimeout(res, 1000 * (attempt + 1)));
    }
    // Only send them back to Prolific once the data is stored, and only to a real
    // absolute URL — a spec still holding the REPLACE_WITH_PROLIFIC_* placeholder
    // would otherwise be resolved as a RELATIVE path and 404 after the data was
    // already saved.
    const raw = screenedOut ? (spec.screenout_url || spec.completion_url)
                            : spec.completion_url;
    const dest = /^https?:\/\//.test(String(raw || '')) ? raw : null;
    if (ok && dest) {
      location.href = dest;
      return;
    }
    if (ok) {
      const note = raw && !dest
        ? `<p class="reviewnote">Review mode: no Prolific completion URL is ` +
          `configured for this app yet (<code>${esc(raw)}</code>), so you have ` +
          `not been redirected. Your responses were saved.</p>`
        : '';
      root.innerHTML = '<div class="card"><p>' +
        (screenedOut ? 'Thank you — you are not eligible for this study, but your ' +
                       'response was recorded and you will be paid for your time.'
                     : 'Done — thank you. Your responses were saved.') +
        ' You may close this window.</p>' + note + '</div>';
    } else {
      root.innerHTML = '<div class="card"><p>We could not save your responses. ' +
        'Please message us on Prolific and do not close this window yet.</p></div>';
    }
  }

  render();
}
