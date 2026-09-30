"""Rebuild the Prolific listings' spec.json from the reconstructions alone.

The fielded specs had been cut down from the reconstructions by a converter that is
not in this repository (mega_archive_replicate/replication/battery_build.py). Where it
dropped items, invented or lost randomisation, flattened branching or mislabelled a
listing, the re-run would test the converter rather than the reconstruction. This
script re-derives the affected listings from final/experiment_N.json and nothing else
— no raw deposit, no paper — under four rules:

1. Items are the reconstruction's, verbatim, in the reconstruction's order, from the
   start of the instrument up to the listing's last outcome item. What followed the
   outcome cannot have shaped it and stays out, as before. Consent and debrief stay
   with the site.
2. Randomisation only where the reconstruction records it (study-metadata.design, or
   testcase/study_context.md); otherwise the reconstruction's order is kept.
3. Branching, piping and same-page layout only where the reconstruction records them.
4. No item text or scale is changed; an error there is the reconstruction's and is
   what the re-run measures.

Listings not rebuilt here (cse5r, kfrux, ba65f_B) had no conversion error that the
reconstruction alone can correct.

The reconstructions are read from a behavioral_archive checkout: --archive PATH, or
$BA_ARCHIVE, or ../behavioral_archive beside this repository.

    python3 tools/respec_battery.py            # rewrite the specs in place
    python3 tools/respec_battery.py --check    # print what would change, write nothing
"""
import collections
import copy
import difflib
import json
import os
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]


def _archive():
    if '--archive' in sys.argv:
        return Path(sys.argv[sys.argv.index('--archive') + 1])
    return Path(os.environ.get('BA_ARCHIVE', SITE.parent / 'behavioral_archive'))


def _studies():
    # an unpacked prolific_battery_v1 beside the site (as downloaded) is used when
    # no archive checkout is given
    if '--archive' not in sys.argv and 'BA_ARCHIVE' not in os.environ \
            and (SITE / 'prolific_battery_v1/studies').is_dir():
        return SITE / 'prolific_battery_v1/studies'
    return _archive() / 'runs/replication/prolific_battery_v1/studies'


STUDIES = _studies()

KEEP = ('type', 'variable-name', 'question', 'content', 'response-constraints',
        'text_source', 'condition')
# Pages the site supplies itself (consent is spec['consent']; there is no debrief page).
SITE_PAGES = {'consent', 'consent_intro', 'consent_information', 'IC', 'Q17', 'debrief'}


class Recon:
    def __init__(self, study, experiment):
        self.ex = json.loads((STUDIES / study / 'final' / f'{experiment}.json').read_text())
        self.items = {}
        for p in self.ex['data']:
            for it in p['study-content']:
                self.items.setdefault(it['variable-name'], it)

    def people(self, shown=None, **meta):
        """Participants matching `meta`; `shown=(name, prefix)` further keeps those
        whose item `name` began with `prefix`, for a factor the reconstruction
        records only in what was displayed."""
        def saw(p):
            if not shown:
                return True
            name, prefix = shown
            return any(it['variable-name'] == name and
                       (it.get('content') or it.get('question') or '').startswith(prefix)
                       for it in p['study-content'])
        return [p for p in self.ex['data'] if saw(p)
                and all(p['participant-meta'].get(k) == v for k, v in meta.items())]

    def sequence(self, longest=False, shown=None, **meta):
        """The modal presentation order of the matching participants, as their items.

        `longest` takes the fullest path instead, for studies whose orders differ
        only because answers hid items."""
        people = self.people(shown=shown, **meta)
        seqs = collections.Counter(
            tuple(it['variable-name'] for it in p['study-content']) for p in people)
        seq = (max(seqs, key=len) if longest else seqs.most_common(1)[0][0])
        # take each item from a participant on that path, so per-arm text is right
        owner = next(p for p in people
                     if tuple(it['variable-name'] for it in p['study-content']) == seq)
        return [clean(it) for it in owner['study-content']
                if it['variable-name'] not in SITE_PAGES]


def clean(it):
    return {k: copy.deepcopy(it[k]) for k in KEEP if it.get(k) is not None}


#: --full fields the whole arm instead of stopping at the outcome item. The default
#: (False) keeps the original behaviour: what followed the outcome cannot have shaped
#: it, so it is left out. Full scope administers the study as the archive records it
#: end to end, which is what a complete replication means.
FULL = False


def upto(items, last):
    if FULL:
        return items
    names = [it['variable-name'] for it in items]
    return items[:names.index(last) + 1]


def seq(*items):
    return {'type': 'group', 'shuffle': False, 'items': list(items)}


def shuffle(items, pick=None):
    g = {'type': 'group', 'shuffle': True, 'items': list(items)}
    if pick:
        g['pick'] = pick
    return g


def by_name(items):
    return {it['variable-name']: it for it in items}


def shuffle_scales(items, scales):
    """Shuffle the items of each scale in place; `scales` maps a name regex to a
    run key (items sharing a key stay together, as a support/effectiveness pair)."""
    out, i = [], 0
    while i < len(items):
        name = items[i]['variable-name']
        rx = next((r for r in scales if re.fullmatch(r, name)), None)
        if rx is None:
            out.append(items[i])
            i += 1
            continue
        j = i
        while j < len(items) and re.fullmatch(rx, items[j]['variable-name']):
            j += 1
        runs = collections.OrderedDict()
        for it in items[i:j]:
            runs.setdefault(scales[rx](it['variable-name']), []).append(it)
        out.append(shuffle([seq(*r) if len(r) > 1 else r[0] for r in runs.values()]))
        i = j
    return out


def one(name):
    return name


# ---------------------------------------------------------------- per listing

def efk28(spec):
    r = Recon('efk28', 'experiment_2')
    arms = []
    for lab in spec['arm_labels']:
        items = r.sequence(case=int(lab['case']), condition=lab['condition'])
        arms.append(upto(items, f"MQ{lab['case']}"))
    return {'arm_blocks': arms}


def fkrsd(spec):
    r = Recon('fkrsd', 'experiment_3')
    items = upto(r.sequence(longest=True), 'return_home_bad_4')
    # The reconstruction records the listing prompts and refers to each entry by a
    # slot label ("Environment good habit 1"); the fields themselves are not items.
    slots = {
        'habit_good_listing': ('habit', 'good', 'habit'),
        'good_nonhabit_listing': ('nonhabit', 'good', 'non-habit'),
        'habit_bad_intro': ('habit', 'bad', 'habit'),
    }
    labels = {}
    out = []
    for it in items:
        name = it['variable-name']
        if name in slots:
            kind, val, word = slots[name]
            fields = []
            for dom, dlabel in (('env', 'Environment'), ('health', 'Health')):
                for k in (1, 2):
                    label = f'{dlabel} {val} {word} {k}'
                    var = f'{kind}_{dom}_{val}_{k}'
                    labels[label] = var
                    fields.append({
                        'type': 'question', 'variable-name': var, 'question': label,
                        'response-constraints': {'type': 'free-response',
                                                 'single-line': True},
                        'text_source': 'authored',
                        'note': 'Entry field for the slot the reconstruction\'s later '
                                'items name by this label.'})
            out.append({'type': 'page', 'items': [it] + fields})
        else:
            out.append(it)
    by_label = {}
    for it in out:
        text = it.get('question') or ''
        pipe = {lab: var for lab, var in labels.items() if lab in text}
        if pipe:
            it['pipe'] = pipe
        if it.get('variable-name', '').startswith(('drop_habit_', 'good habit_start_',
                                                    'bad habit_start_')):
            by_label[text.split('? ', 1)[1]] = it['variable-name']
    # "follow-up return/keep questions were shown only for likelihood ratings > 50":
    # return_home_* follows the stop rating, keep_newh_* the start rating
    for it in out:
        if it.get('variable-name', '').startswith(('return_home_', 'keep_newh_')):
            gate = by_label[it['question'].split('? ', 1)[1]]
            it['show_if'] = {'variable': gate, 'op': '>', 'value': 50}
    # The reconstruction is internally inconsistent: it records a listing prompt for
    # good non-habits but none for BAD non-habits, while still carrying eight items
    # ("bad habit_start_*", "keep_newh_bad_*") that name bad-non-habit slots. Those
    # slots are never collected, so those items would show a participant the raw
    # label "Environment bad non-habit 1" and ask them to rate a behaviour they were
    # never asked to name. Neither item feeds the target (f67 reads return_home_*).
    # Dropping them records the gap; inventing a fourth listing page would not.
    out = drop_orphan_slots(out, labels)
    return {'blocks': out}


SLOT_LABEL = re.compile(
    r'(Environment|Health)\s+(good|bad)\s+(non-)?habit\s*\d', re.I)


def drop_orphan_slots(blocks, labels):
    """Remove items naming a slot label that no entry field collects.

    An item whose text refers to "Environment bad non-habit 1" is only answerable if
    something earlier asked the participant to name it. Where it did not, the item
    reaches the participant as a raw slot label. Raises if an item is piped but its
    source is missing, which would be a different bug.
    """
    kept, dropped = [], []
    for b in blocks:
        text = b.get('question') or ''
        m = SLOT_LABEL.search(text)
        if (m and m.group(0) not in labels
                and (b.get('response-constraints') or {}).get('type')
                != 'free-response'):
            assert not b.get('pipe'), f"{b.get('variable-name')}: piped but unsourced"
            dropped.append(b['variable-name'])
            continue
        kept.append(b)
    if dropped:
        print(f"           dropped {len(dropped)} item(s) naming an uncollected "
              f"slot: {', '.join(dropped[:4])}"
              + (' ...' if len(dropped) > 4 else ''))
    return kept


def matrix_pages(items):
    """Put a recorded matrix back on one screen.

    The reconstruction records a matrix as an instructions screen followed by rows
    whose question is "<shared stem> — <row label>". Three or more such rows after
    their instructions become one page, as participants saw them."""
    stem = lambda it: (re.match(r'(.{15,}?) — ', it.get('question') or '') or
                       [None, None])[1]
    out, i = [], 0
    while i < len(items):
        it = items[i]
        j = i + 1
        if it['type'] == 'stimuli' and j < len(items) and stem(items[j]):
            while j < len(items) and stem(items[j]) == stem(items[i + 1]):
                j += 1
            if j - i - 1 >= 3:
                out.append({'type': 'page', 'items': items[i:j]})
                i = j
                continue
        out.append(it)
        i += 1
    return out


def sixfjdr(spec):
    r = Recon('6fjdr', 'experiment_1')
    return {'blocks': matrix_pages(upto(r.sequence(), 'Impact_vegetarian'))}


def branch_merge(paths, var):
    """Align two branches' presentation orders into one gated sequence.

    `paths` maps each of the two answers of `var` to that branch's item sequence.
    Items both branches show, in the same place, are asked unconditionally; the runs
    only one branch shows are gated on `var`. No item moves relative to its
    neighbours on either path."""
    (va, a), (vb, b) = paths.items()
    names = lambda seq: [it['variable-name'] for it in seq]
    gate = lambda val, it: dict(it, show_if={'variable': var, 'op': '==', 'value': val})
    out = []
    ops = difflib.SequenceMatcher(None, names(a), names(b), autojunk=False).get_opcodes()
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            out += a[i1:i2]
        else:
            out += [gate(va, it) for it in a[i1:i2]] + [gate(vb, it) for it in b[j1:j2]]
    return out


def sixcxdn(spec):
    r = Recon('6cxdn', 'experiment_2')
    partnered = r.sequence(analysis_relationship_group='partnered')
    single = r.sequence(analysis_relationship_group='single')
    status = next(it for it in _items(spec['blocks'])
                  if it['variable-name'] == 'relationship_status')
    status = {k: v for k, v in status.items() if k != 'show_if'}
    status['note'] = (
        'Authored. The reconstruction branches on participant-meta.'
        'analysis_relationship_group, which no archive item asks; this question '
        'stands in for it and is asked first, so each branch is taken before its '
        'items (Yes = partnered, No = single).')
    # The reconstruction's items name the person as "<initials>", the original
    # survey's piped entry; nothing in the reconstruction collects it.
    initials = {
        'type': 'question', 'variable-name': 'partner_initials',
        'question': 'Please type the initials of the person you will answer about: '
                    'your current romantic partner or, if you are single, a person '
                    'you have romantic interest in or have recently dated in person.',
        'response-constraints': {'type': 'free-response', 'single-line': True,
                                 'response-limit': 10},
        'text_source': 'authored',
        'note': 'Entry field for the "<initials>" slot the reconstruction\'s later '
                'items refer to.'}
    body = branch_merge({'Yes': upto(partnered, 'RoCh.31'),
                         'No': upto(single, 'RoCh.31')}, 'relationship_status')
    for it in body:
        if '<initials>' in (it.get('question') or '') + (it.get('content') or ''):
            it['pipe'] = {'<initials>': 'partner_initials'}
    return {'blocks': [status, initials] + body}


def ninebhq_s1(spec):
    r = Recon('9ebhq', 'experiment_1')
    items = upto(r.sequence(), 'proven.CTS5.')
    n = [it['variable-name'] for it in items]
    a, b = n.index('informed_instructions'), n.index('proven_instructions')
    # "order of perceived-knowledge and proven/disproven scales was randomized"
    return {'blocks': items[:a] + [shuffle([seq(*items[a:b]), seq(*items[b:])])],
            'target': 'f06'}


def ninebhq_s2(spec):
    r = Recon('9ebhq', 'experiment_2')
    return {'blocks': upto(r.sequence(), 'informed.MU3.')}


HVDWK_SCALES = {
    r'PComp__\d+': one, r'SK_complexity_\d+': one, r'CR_efficacy_\d+': one,
    r'CCS_\d+': one, r'polsupport_\d+': one, r'behintent_\d+': one, r'NFC_\d+': one,
    r'behaviors_\d+': one,
    # Study 2 asked each policy as a support/effectiveness pair
    r'(airtravel_|cartolls|trainsubsidies_|publictransit|meat_tax|subsidizePB|'
    r'renewables_default|carbonlabel|co2tax)_\d': lambda n: n.rsplit('_', 1)[0],
    r'(pesticides|recycled|boycott|chemicals|taxes|compromise|voting)_\d':
        lambda n: n.rsplit('_', 1)[0],
}


def hvdwk_s2(spec):
    r = Recon('hvdwk', 'experiment_2')
    # "Item order within each scale was randomized per participant"
    return {'blocks': shuffle_scales(upto(r.sequence(), 'worry_'), HVDWK_SCALES),
            'target': 'f19'}


def hvdwk_s3(spec):
    r = Recon('hvdwk', 'experiment_3')
    return {'blocks': shuffle_scales(upto(r.sequence(), 'worry_'), HVDWK_SCALES)}


def aj5mt(spec):
    r = Recon('aj5mt', 'experiment_1')
    decks = sorted({p['participant-meta']['counterbalanced_condition']
                    for p in r.ex['data']})
    return {'arms': len(decks), 'arm_keys': ['deck'],
            'arm_labels': [{'deck': str(d)} for d in decks],
            'arm_blocks': [upto(r.sequence(counterbalanced_condition=d), '18_C1_4')
                           for d in decks]}


def ba65f_a(spec):
    r = Recon('ba65f', 'experiment_1')
    items = r.sequence(group='A')
    out, situations = [], collections.OrderedDict()
    for it in items:
        m = re.match(r'([A-Za-z]+)_(situation|Prior|High|Low)', it['variable-name'])
        if not m:
            out.append(it)
            continue
        situations.setdefault(m.group(1), collections.defaultdict(list))[
            m.group(2)].append(it)
    runs = []
    for s in situations.values():
        # "Group A action order randomized"
        runs.append(seq(*s['situation'], *s['Prior'],
                        shuffle([seq(*s['High']), seq(*s['Low'])])))
    # "10 vignettes presented in random order"
    return {'blocks': out + [shuffle(runs)]}


def dqsv6(spec):
    r = Recon('dqsv6', 'experiment_1')
    items = r.sequence()
    # "items in each measure were presented in random order"
    scales = {rx: one for rx in (r'ID\d', r'CN\d', r'(Anarch|Pacyf)\d', r'Glob\d',
                                 r'RWA\d', r'SDO\d')}
    return {'blocks': shuffle_scales(upto(items, 'politicalconservatism'), scales)}


def ky9u6(spec):
    r = Recon('ky9u6', 'experiment_1')
    return {'blocks': upto(r.sequence(), 'mhc.14')}


def kf4e6(spec):
    r = Recon('kf4e6', 'experiment_1')
    arms = []
    for lab in spec['arm_labels']:
        code = {'conjunctive': 'C', 'disjunctive': 'D'}[lab['causal_structure']] + '_' + \
            {'action': 'A', 'inaction': 'I'}[lab['action_type']]
        items = upto(r.sequence(condition_code=code), f'{code}_1')
        # "one causal-agreement rating shown on the same page as the vignette"
        arms.append(items[:-2] + [{'type': 'page', 'items': items[-2:]}])
    return {'arm_blocks': arms}


#: The manipulated-goal arm's framing is recorded only as the text of
#: `mindset_framing`; a modal path per arm kept the credibility framing alone.
FXP7G_GOALS = {'credibility': 'Imagine that you’re online with a purpose: you want to '
                              'find credible',
               'enjoyment': 'Imagine you’re browsing the internet with a purpose: you '
                            'want to find entertaining'}


def fxp7g(spec):
    r = Recon('fxp7g', 'experiment_4')
    cells = []
    for c in ['control', 'manipulated_goal', 'measured_goal', 'measured_site_preference']:
        for goal in (FXP7G_GOALS if c == 'manipulated_goal' else [None]):
            cells.append((c, goal))
    labels, arms = [], []
    for c, goal in cells:
        for s in (1, 2):
            shown = ('mindset_framing', FXP7G_GOALS[goal]) if goal else None
            items = r.sequence(condition=c, set=s, shown=shown)
            first = next(i for i, it in enumerate(items)
                         if it['variable-name'].startswith('likelihood_sentiment_h'))
            runs = collections.OrderedDict()
            for it in items[first:]:
                runs.setdefault(it['variable-name'].rsplit('_h', 1)[1], []).append(it)
            labels.append({'condition': c, 'set': str(s), 'goal': goal or ''})
            # "headline order randomized"
            arms.append(items[:first] + [shuffle([seq(*v) for v in runs.values()])])
    return {'arms': len(arms), 'arm_keys': ['condition', 'set', 'goal'],
            'arm_labels': labels, 'arm_blocks': arms}


def kxcwm(spec):
    r = Recon('kxcwm', 'experiment_1')
    timed = {}
    for it in _items(spec.get('arm_blocks') or spec['blocks']):
        if it['type'] == 'timed-ideas':
            timed.setdefault(it['variable-name'], it)
    rest = r.sequence()
    names = [it['variable-name'] for it in rest]
    tail = upto(rest[names.index('csb_instructions'):], 'idiff_hps_48')

    def task(t):
        runs = []
        for name, ti in timed.items():
            if name.startswith(f'idea_{t}_'):
                p = name[len('idea_'):]
                runs.append(seq(ti, clean(r.items[f'selfeval_{p}']),
                                clean(r.items[f'cogload_{p}'])))
        # "4 prompts drawn at random from 16": two per task
        return [clean(r.items[f'instructions_{t}']), shuffle(runs, pick=2)]

    # "order of Alternate Uses vs Consequences task blocks counterbalanced"
    return {'arms': 2, 'arm_keys': ['task_order_condition'],
            'arm_labels': [{'task_order_condition': 'aut_ct'},
                           {'task_order_condition': 'ct_aut'}],
            'arm_blocks': [task('aut') + task('ct') + tail,
                           task('ct') + task('aut') + tail]}


def _items(b, out=None):
    out = [] if out is None else out
    if isinstance(b, dict):
        if b.get('type') in ('stimuli', 'question', 'timed-ideas'):
            out.append(b)
        for v in b.get('items', []):
            _items(v, out)
    elif isinstance(b, list):
        for x in b:
            _items(x, out)
    return out


def kfrux(spec):
    """Three scenario conditions; one rating to the outcome, five items in full."""
    r = Recon('kfrux', 'experiment_1')
    labs = [l['condition'] for l in spec['arm_labels']]
    return {'arm_blocks': [upto(r.sequence(condition=c), 'creativity') for c in labs]}


def cse5r(spec):
    """Representation-goals vs control; the nomination task then its ratings."""
    r = Recon('cse5r', 'experiment_1')
    labs = [l['condition'] for l in spec['arm_labels']]
    arms = []
    for c in labs:
        # the fullest path: org_goals, goals and endorse_* follow only a "Yes" to
        # `initiative` (all 458 who saw them answered Yes, none of the 527 who did not)
        items = upto(r.sequence(longest=True, condition=c), 'asn_womn')
        for it in items:
            if it['variable-name'] in CSE5R_FOLLOWUPS:
                it['show_if'] = {'variable': 'initiative', 'op': '==', 'value': 'Yes'}
        arms.append(items)
    return {'arm_blocks': arms}


CSE5R_FOLLOWUPS = {'org_goals', 'goals', 'endorse_sup', 'endorse_org', 'endorse_personally'}


def ba65f_b(spec):
    """Group B as built: every item already matches the reconstruction. Only the
    site's own closing items are refreshed, as for every listing."""
    return {'blocks': strip_site(spec['blocks'])}


# ---------------------------------------------------------------- site additions
#
# Items the site adds after each listing's instrument. They come after every
# reconstruction item, so they cannot shape an outcome, and each carries
# `text_source: "site"` so a rebuild strips and re-adds them rather than stacking.

ATTENTION = {
    'type': 'question', 'variable-name': 'site_attention_check',
    'question': 'It is important that you read each question carefully. To show that '
                'you are reading, please select "Disagree" for this question.',
    'response-constraints': {'type': 'mcq', 'options': [
        'Strongly disagree', 'Disagree', 'Neither agree nor disagree', 'Agree',
        'Strongly agree'], 'max-choices': 1},
    'text_source': 'site',
    'note': 'Instructed-response check. None of the reconstructions carries the '
            'original checks, so the original exclusions cannot be reapplied; this '
            'one is recorded, not used to screen out. Pass = "Disagree".'}

DEMO_TEXT = {
    'age': 'What is your age (in years)?',
    'gender': 'What is your gender?',
    'education': 'What is the highest level of education you have completed?',
    'income': 'What is your annual household income?',
    'household_income': 'What is your annual household income?',
    'employment': 'What is your current employment status?',
    'occupation': 'What is your current occupation?',
    'political_orientation': 'How would you describe your political orientation?',
}
#: Numeric fields are fielded only where their scale is documented; an undocumented
#: anchor could reverse the coding.
DEMO_SCALES = {
    ('hvdwk', 'political_orientation'): (1, 7, 'Left-wing', 'Right-wing'),
    ('9ebhq', 'education'): (1, 5, 'No formal education',
                             'College education, graduate degree'),
}


def demographics(study, experiment):
    """The participant-info fields this study's findings or tests read, asked with
    the archive's own answer categories so no recoding is needed. Age and gender
    are always asked. Each item is named `participant-info.<field>`, the path the
    findings use."""
    d = STUDIES / study
    used = set(re.findall(r'participant-info\.([A-Za-z_0-9]+)',
                          (d / 'testcase/findings.json').read_text()))
    used |= set(re.findall(r'participant[-_]info[\'"]?\]?\s*(?:\.get\(|\[)\s*'
                           r'[\'"]([A-Za-z_0-9]+)',
                           (d / 'testcase/reproduction_tests.py').read_text()))
    ex = json.loads((d / 'final' / f'{experiment}.json').read_text())
    values = collections.defaultdict(list)
    for p in ex['data']:
        for k, v in (p.get('participant-info') or {}).items():
            values[k].append(v)
    out = []
    for key in ['age', 'gender'] + sorted(used - {'age', 'gender'}):
        vals = [v for v in values.get(key, []) if v not in (None, '')]
        if key == 'gender' and not vals:
            vals = ['woman', 'man', 'non-binary', 'prefer not to say']
        if key not in DEMO_TEXT or (not vals and key != 'age'):
            continue
        item = {'type': 'question', 'variable-name': f'participant-info.{key}',
                'question': DEMO_TEXT[key], 'text_source': 'site'}
        scale = DEMO_SCALES.get((study, key))
        if key == 'age':
            item['response-constraints'] = {'type': 'free-response',
                                            'single-line': True, 'response-limit': 3}
        elif scale:
            lo, hi, lo_d, hi_d = scale
            item['response-constraints'] = {'type': 'scalar', 'scale-min': lo,
                                            'scale-max': hi, 'scale-min-desc': lo_d,
                                            'scale-max-desc': hi_d}
            item['note'] = 'Archive codes this field as its scale point.'
        else:
            flat = [x for v in vals for x in (v if isinstance(v, list) else [v])]
            if any(not isinstance(x, str) for x in flat):
                continue          # numeric with no documented scale
            opts = list(collections.Counter(flat))
            if len(opts) > 12:
                continue          # free-text field in the archive; not a category
            item['response-constraints'] = {
                'type': 'mcq', 'options': opts,
                'max-choices': len(opts) if any(isinstance(v, list) for v in vals) else 1}
        out.append(item)
    return out


def strip_site(blocks):
    if isinstance(blocks, list):
        return [strip_site(b) for b in blocks
                if not (isinstance(b, dict) and b.get('text_source') == 'site')]
    if isinstance(blocks, dict) and 'items' in blocks:
        return dict(blocks, items=strip_site(blocks['items']))
    return blocks


def add_site_items(spec):
    tail = [ATTENTION] + demographics(spec['study'], spec['archive_experiment'])
    if 'arm_blocks' in spec:
        spec['arm_blocks'] = [strip_site(a) + copy.deepcopy(tail)
                              for a in spec['arm_blocks']]
    else:
        spec['blocks'] = strip_site(spec['blocks']) + copy.deepcopy(tail)
    return spec


# ---------------------------------------------------------------- listing settings

#: What the consent's DESCRIPTION says the participant will do; {q} is the number
#: of questions on the longest path, counted from the built instrument.
CONSENT_TASK = {
    'kfrux': 'read a short scenario about a fashion designer and answer {q} questions',
    'kf4e6': 'read a short passage about a streaming service\'s policy and answer {q} '
             'questions',
    'efk28': 'read a short story about a person\'s life and answer {q} questions',
    'cse5r': 'read a short workplace scenario and answer up to {q} questions about it and '
             'about your own workplace',
    '6fjdr': 'answer {q} questions about climate change and about actions people take '
             'to reduce their carbon footprint',
    'fkrsd': 'name some of your own habits and behaviours and answer up to {q} '
             'questions about how a holiday might change them',
    '6cxdn': 'answer up to {q} questions about a current romantic partner or a person '
             'you are romantically interested in',
    'ba65f_A': 'read ten short scenarios about two friends and answer {q} questions '
               'about them',
    'ba65f_B': 'read ten short scenarios about two friends and answer {q} questions '
               'about them',
    'aj5mt': 'read short descriptions of people and answer {q} questions about how '
             'likely certain statements are and how confident you feel',
    'dqsv6': 'answer {q} questions about your views on Britain, on international '
             'affairs, and on how a country should be governed',
    '9ebhq_S1': 'read a number of widely discussed claims and answer {q} questions '
                'about how much you agree with them, how much you know about them, '
                'and whether they have been proven or disproven',
    '9ebhq_S2': 'read a number of widely discussed claims and answer {q} questions '
                'about them and about your personality and ways of thinking',
    'fxp7g': 'read eight news headlines and answer {q} questions about them',
    'ky9u6': 'answer {q} questions about your personality, your personal projects and '
             'how you have been feeling',
    'hvdwk_S2': 'answer {q} questions about environmental sustainability',
    'hvdwk_S3': 'answer {q} questions about environmental sustainability',
    'kxcwm': 'complete {t} two-minute timed tasks in which you type as many ideas as '
             'you can, rate your own ideas, and answer {q} questions in total, '
             'including true/false questions about yourself',
}
#: Content a participant should know about before consenting, beyond the task.
CONSENT_NOTES = {
    '6cxdn': ['The questions ask about closeness and intimacy in your relationship. '
              'If you are in a relationship, some questions ask about your sexual '
              'relationship and sexual satisfaction.'],
}

#: Prolific settings that differ from the built listing, taken from each study's
#: recruitment as the archive describes it (testcase/study_context.md).
PRESCREEN = {
    'fkrsd': {'min_age': 18},       # "adults"; Studies 1-2 "aged 18 or older"
    'kf4e6': {'approval_rate_min': 99, 'nationality': ['United States'],
              'country_of_birth': ['United States'], 'first_language': ['English'],
              'exclude_prior_listings': True},
    'dqsv6': {'nationality': ['United Kingdom']},     # "British sample"
    '6cxdn': {'quotas': [{'filter': 'Relationship status',
                          'groups': {'single': 0.5, 'in a relationship': 0.5}}],
              'other': ['fluent English']},
    '9ebhq_S1': {'quotas': [{'filter': 'COVID-19 vaccination',
                             'groups': {'not vaccinated (declined)': 0.5,
                                        'no prescreen': 0.5}}]},
    '9ebhq_S2': {'quotas': [{'filter': 'Sex', 'groups': {'female': 0.5, 'male': 0.5}},
                            {'filter': 'Political affiliation (US)',
                             'groups': {'Democrat': 0.34, 'Republican': 0.33,
                                        'Independent': 0.33}}],
                 'representative_on': ['gender', 'age', 'political partisanship']},
    'cse5r': {'employment_status': ['Full-Time']},
    '6fjdr': {'analysis_filter': 'climate_worry_1 >= 4 (the original screener; '
                                 'worry < 4 is excluded at analysis, not screened out)'},
}


def count_questions(spec):
    """(questions, timed tasks) on the longest arm, counting every gated item."""
    best = (0, 0)
    for blocks in spec.get('arm_blocks') or [spec['blocks']]:
        shown = _shown(blocks)
        best = max(best, (sum(it['type'] == 'question' for it in shown),
                          sum(it['type'] == 'timed-ideas' for it in shown)))
    return best


def refresh_description(spec):
    q, t = count_questions(spec)
    words = {2: 'two', 3: 'three', 4: 'four'}
    task = CONSENT_TASK[spec['app']].format(q=q, t=words.get(t, t))
    out = []
    for head, paras in spec.get('consent_sections') or []:
        if head and 'DESCRIPTION' in head:
            paras = list(paras)
            paras[0] = re.sub(r'You will be asked to .*?\. There are no',
                              f'You will be asked to {task}. There are no', paras[0])
            paras = [p for p in paras if p not in CONSENT_NOTES.get(spec['app'], [])
                     and not p.startswith('The questions ask about closeness')]
            age = spec['prescreen'].get('min_age', 18)
            paras = [re.sub(r'You must be \d+ or older', f'You must be {age} or older', p)
                     for p in paras]
            k = next((i for i, p in enumerate(paras) if p.startswith('You must be')),
                     len(paras))
            paras[k:k] = CONSENT_NOTES.get(spec['app'], [])
        out.append([head, paras])
    spec['consent_sections'] = out
    return spec


def apply_prescreen(spec):
    spec['prescreen'] = {**spec.get('prescreen', {}), **PRESCREEN.get(spec['app'], {})}
    return spec


def mark_timed(spec):
    """The original idea tasks ran for their full time ("participants could not
    advance early"); the renderer honours `lock` by offering no early exit."""
    for it in _items(spec.get('arm_blocks') or spec.get('blocks')):
        if it['type'] == 'timed-ideas':
            it['lock'] = True
    return spec


LISTINGS = {
    'kfrux': kfrux, 'cse5r': cse5r, 'efk28': efk28, 'fkrsd': fkrsd, '6fjdr': sixfjdr, '6cxdn': sixcxdn,
    '9ebhq_S1': ninebhq_s1, '9ebhq_S2': ninebhq_s2, 'hvdwk_S2': hvdwk_s2,
    'hvdwk_S3': hvdwk_s3, 'aj5mt': aj5mt, 'ba65f_A': ba65f_a, 'dqsv6': dqsv6,
    'ky9u6': ky9u6, 'kf4e6': kf4e6, 'fxp7g': fxp7g, 'kxcwm': kxcwm,
    'ba65f_B': ba65f_b,
}


# ---------------------------------------------------------------- session length

def _load(listing):
    return json.loads((SITE / listing / 'spec.json').read_text())


def _size(spec):
    """(words, questions, timed seconds) of the longest arm."""
    best = (0, 0, 0)
    for blocks in spec.get('arm_blocks') or [spec['blocks']]:
        words = qs = timed = 0
        for it in _shown(blocks):
            words += len(re.findall(r'\w+', (it.get('question') or '') +
                                    ' ' + (it.get('content') or '')))
            qs += it['type'] == 'question'
            timed += it.get('duration_ms', 0) / 1000
        best = max(best, (words, qs, timed))
    return best


def _shown(b):
    if isinstance(b, list):
        return [x for c in b for x in _shown(c)]
    if b.get('type') in ('group',) and b.get('pick'):
        runs = b['items'][:b['pick']]
        return [x for c in runs for x in _shown(c)]
    if b.get('type') in ('group', 'page', 'interleave'):
        return [x for c in b['items'] for x in _shown(c)]
    if b.get('type') == 'balanced':
        return [x for c in b['items'] for x in _shown(c['items'][0])]
    return [b]


# estimated_minutes as the old converter set them, recovered by least squares over the
# listings it priced above the $0.60 floor (words, questions, seconds of timed task);
# it reproduces those listings' minutes to within ~15%. Fitted once on the committed
# specs so a rerun of this script does not refit on its own output.
MIN_PER_WORD, MIN_PER_QUESTION, MIN_PER_TIMED_SECOND = 0.00057, 0.1817, 0.0144


def refresh_consent(spec):
    """Keep the in-study consent text in step with the recomputed time and pay.

    respec carries `consent` over from the previous spec, so a listing whose
    instrument grew would otherwise promise the old duration and the old payment on
    the first screen a participant sees. Only those two sentences are rewritten; the
    rest of the form, including the GDPR block, is untouched.
    """
    mins = spec['estimated_minutes']
    phrase = 'one minute' if mins < 1.5 else f'{int(round(mins))} minutes'
    time_txt = f'Your participation will take approximately {phrase}.'
    pay_txt = (f'You will receive ${spec["reward_usd"]:.2f}, paid through Prolific, '
               f'as payment for your participation.')
    out = []
    for head, paras in spec.get('consent_sections') or []:
        if head == 'TIME INVOLVEMENT:':
            paras = [time_txt]
        elif head == 'PAYMENTS:':
            paras = [pay_txt]
        out.append([head, paras])
    spec['consent_sections'] = out
    spec['consent'] = ''.join(
        (f'<h4>{h}</h4>' if h else '') + ''.join(f'<p>{p}</p>' for p in ps)
        for h, ps in out)
    return spec


URL = ('https://stanfordai4hi.github.io/prolific-reconstruction/{}/?PROLIFIC_PID='
       '{{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}')


def write_settings(specs):
    """PROLIFIC_SETTINGS.md and the README table, both from the specs, so the
    listing time and pay on Prolific cannot drift from what the consent promises."""
    readme = (SITE / 'README.md').read_text()
    rows = re.findall(r'^\| (\d+) \| `([^`]+)` \| ([^|]+?) \| (\d+) \| [\d.]+ \|$',
                      readme, re.M)
    places = {name: int(n) for _, name, _, n in rows}
    for num, name, title, n in rows:
        mins = int(round(specs[name]['estimated_minutes'])) if name in specs else None
        if mins is not None:
            readme = re.sub(rf'^\| {num} \| `{re.escape(name)}` \| .*$',
                            f'| {num} | `{name}` | {title} | {n} | {max(mins, 1)} |',
                            readme, flags=re.M)
    (SITE / 'README.md').write_text(readme)

    out = ['# Prolific settings', '',
           'Generated by `tools/respec_battery.py` from each `spec.json`; do not edit by '
           'hand. Completion time and reward must match the consent screen, which is '
           'regenerated from the same numbers.', '',
           'Every listing: completion URL from proliferate, "exclude participants from '
           'previous listings" on for all eighteen (one Prolific participant group), '
           'desktop and mobile allowed.', '']
    for _, name, title, _ in rows:
        sp = specs[name]
        ps = sp.get('prescreen', {})
        n = places[name]
        out += [f'## `{name}` — {sp["title"]}', '',
                f'- **Places:** {n}' + (f' ({sp["arms"]} arms, ~{n // sp["arms"]} per arm)'
                                         if sp.get('arms') else ''),
                f'- **Completion time:** {max(int(round(sp["estimated_minutes"])), 1)} min '
                f'(estimate {sp["estimated_minutes"]})',
                f'- **Reward:** ${sp["reward_usd"]:.2f}',
                f'- **Study URL:** `{URL.format(name)}`']
        filt = [f'Country of residence: {", ".join(ps["countries"])}' if ps.get('countries') else None,
                f'Age: {ps.get("min_age", 18)}+',
                f'Nationality: {", ".join(ps["nationality"])}' if ps.get('nationality') else None,
                f'Country of birth: {", ".join(ps["country_of_birth"])}' if ps.get('country_of_birth') else None,
                f'First language: {", ".join(ps["first_language"])}' if ps.get('first_language') else None,
                f'Employment status: {", ".join(ps["employment_status"])}' if ps.get('employment_status') else None,
                f'Approval rate: ≥ {ps["approval_rate_min"]}%' if ps.get('approval_rate_min') else None]
        out.append('- **Filters:** ' + '; '.join(f for f in filt if f))
        for q in ps.get('quotas', []):
            out.append(f'- **Quota ({q["filter"]}):** ' + ', '.join(
                f'{k} {round(v * n)}' for k, v in q['groups'].items()))
        if ps.get('representative_on'):
            out.append('- **Original sample was representative on:** '
                       + ', '.join(ps['representative_on']))
        for o in ps.get('other', []):
            out.append(f'- **Also:** {o}')
        if ps.get('analysis_filter'):
            out.append(f'- **Analysis filter:** {ps["analysis_filter"]}')
        out.append('')
    (SITE / 'PROLIFIC_SETTINGS.md').write_text('\n'.join(out))


def main():
    global FULL
    check = '--check' in sys.argv
    FULL = '--full' in sys.argv
    built = {}
    for name, build in LISTINGS.items():
        old = _load(name)
        new = copy.deepcopy(old)
        for k in ('blocks', 'arms', 'arm_keys', 'arm_labels', 'arm_blocks'):
            new.pop(k, None)
        new.update(build(old))
        if 'arm_blocks' in new and 'arms' not in new:
            new['arms'] = old['arms']
            new['arm_keys'], new['arm_labels'] = old['arm_keys'], old['arm_labels']
        add_site_items(new)
        mark_timed(new)
        apply_prescreen(new)
        refresh_description(new)
        w, q, t = _size(new)
        # never below what the listing already promised: pay is not cut for a
        # listing whose content did not shrink
        minutes = max(old['estimated_minutes'],
                      round(MIN_PER_WORD * w + MIN_PER_QUESTION * q
                            + MIN_PER_TIMED_SECOND * t, 1))
        new['estimated_minutes'] = minutes
        new['reward_usd'] = (old['reward_usd'] if minutes == old['estimated_minutes']
                             else max(old['reward_usd'], round(max(0.6, 0.2 * minutes), 2)))
        refresh_consent(new)
        order = ['app', 'study', 'archive_experiment', 'target', 'title', 'arms',
                 'arm_keys', 'arm_labels', 'arm_blocks', 'blocks']
        new = {**{k: new[k] for k in order if k in new},
               **{k: v for k, v in new.items() if k not in order}}
        print(f"{name:9} target {old['target']}->{new['target']}  "
              f"items/arm {len(_items(old.get('arm_blocks', [old.get('blocks')])[0]))}"
              f"->{len(_items((new.get('arm_blocks') or [new['blocks']])[0]))}  "
              f"arms {old.get('arms', 1)}->{new.get('arms', 1)}  "
              f"min {old['estimated_minutes']}->{minutes}  "
              f"usd {old['reward_usd']}->{new['reward_usd']}")
        built[name] = new
        if not check:
            (SITE / name / 'spec.json').write_text(
                json.dumps(new, indent=1, ensure_ascii=False) + '\n')
    if not check:
        write_settings(built)


if __name__ == '__main__':
    main()
