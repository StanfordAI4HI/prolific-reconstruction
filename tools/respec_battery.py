"""Rebuild the Prolific listings' spec.json from the reconstructions alone.

The fielded specs had been cut down from the reconstructions by a converter that is
not in this repository (mega_archive_replicate/replication/battery_build.py). Where it
dropped items, invented or lost randomisation, flattened branching or mislabelled a
listing, the re-run would test the converter rather than the reconstruction. This
script re-derives the listings from the reconstruction records and nothing else — no
raw deposit, no paper — under four rules:

1. Items are the reconstruction's, verbatim, in the reconstruction's order, from the
   start of the instrument up to the listing's last outcome item. What followed the
   outcome cannot have shaped it and stays out, as before. Consent and debrief stay
   with the site.
2. Randomisation only where the reconstruction records it (the study's design notes);
   otherwise the reconstruction's order is kept.
3. Branching, piping and same-page layout only where the reconstruction records them.
4. No item text or scale is changed; an error there is the reconstruction's and is
   what the re-run measures.

Records. Eleven studies are read from the revised `ba/3` records (data1030:
`<id>/data/study_N.json`); the other four (efk28, 6fjdr, 6cxdn, ky9u6) have no revised
record and are still read from the v1 battery's `final/experiment_N.json`. From a ba/3
record this script

- takes only people the record does not flag in `participant-meta.excluded` when
  choosing a path (the revision restored excluded people as flagged rows);
- skips items marked `is-measured` (e.g. aj5mt's response times): those are measured,
  not asked, and the renderer records `rt_ms` for every answer instead;
- skips the reconstruction's narration — `synthesized` stimuli written in the second
  person ("You type your four good habits into four boxes...") that describe a step
  whose material was not deposited. They are not something a participant can be
  shown. A listing replaces one with a real item only where the record gives the
  wording (kxcwm's attention statements) or the step is a plain entry box (fkrsd), and
  marks the replacement `authored` or with its source;
- turns `shown-if` on an earlier answer into the renderer's `show_if`; a `shown-if` on
  an assignment is what the arm (or a random pick inside it) already decides.

The reconstructions are read from: --records PATH (or $BA_RECORDS, or
../../data1030/records beside the deploy checkout) for ba/3, and --archive PATH (or
$BA_ARCHIVE, or ../behavioral_archive) for the v1 battery.

    python3 tools/respec_battery.py --full     # rewrite the specs in place
    python3 tools/respec_battery.py --check    # print what would change, write nothing
"""
import collections
import copy
import json
import os
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]


def _arg(flag, env, default):
    if flag in sys.argv:
        return Path(sys.argv[sys.argv.index(flag) + 1])
    return Path(os.environ.get(env, default))


LEGACY = _arg('--archive', 'BA_ARCHIVE', SITE.parent / 'behavioral_archive') / \
    'runs/replication/prolific_battery_v1/studies'
RECORDS = _arg('--records', 'BA_RECORDS', SITE.parent.parent / 'data1030' / 'records')

KEEP = ('type', 'variable-name', 'question', 'content', 'response-constraints',
        'text_source', 'condition', 'check')
# Pages the site supplies itself (consent is spec['consent']; there is no debrief page).
SITE_PAGES = {'consent', 'consent_intro', 'consent_information', 'IC', 'Q17', 'debrief',
              'Informed_consent'}
NARRATION = re.compile(r'(You|For each)\b')


def narration(it):
    return (it.get('text-source') == 'synthesized' and it['type'] == 'stimuli'
            and bool(NARRATION.match(it.get('content') or '')))


def clean(it):
    out = {k: copy.deepcopy(it[k]) for k in KEEP if it.get(k) is not None}
    if it.get('text-source'):
        out['text_source'] = it['text-source']
    gate = [c for c in (it.get('shown-if') or {}).get('criteria', []) if 'item' in c]
    if gate:
        assert len(gate) == 1, f"{it['variable-name']}: compound gate {gate}"
        c = gate[0]
        out['show_if'] = {'variable': c['item'], 'op': c['op'], 'value': c.get('value')}
    for k in ('show_if', 'pipe', 'note'):          # set by a listing on a replacement
        if k in it and k not in out:
            out[k] = copy.deepcopy(it[k])
    return out


def _names(path):
    return tuple(it['variable-name'] for it in path)


def _gated(it):
    return any('item' in c for c in (it.get('shown-if') or {}).get('criteria', []))


class Record:
    """One study of a ba/3 record (data1030)."""

    def __init__(self, study, n):
        doc = json.loads((RECORDS / study / 'data' / f'study_{n}.json').read_text())
        self.study, self.n = study, n
        self.data = [p for p in doc['data'] if not p['participant-meta'].get('excluded')]
        self.items = {}
        for p in self.data:
            for it in p['study-content']:
                self.items.setdefault(it['variable-name'], it)

    def people(self, **meta):
        return [p for p in self.data
                if all(p['participant-meta'].get(k) == v for k, v in meta.items())]

    def path(self, longest=False, **meta):
        """The modal (or fullest) path of the matching people, with every item that an
        earlier answer gates merged in where it was shown — so both sides of a branch
        are fielded and the renderer takes it."""
        people = self.people(**meta)
        assert people, f'{self.study} S{self.n}: nobody matches {meta}'
        seqs = collections.Counter(_names(p['study-content']) for p in people)
        top = max(seqs, key=len) if longest else seqs.most_common(1)[0][0]
        out = list(next(p for p in people if _names(p['study-content']) == top)
                   ['study-content'])
        have = list(top)
        for p in people:
            prev = None
            for it in p['study-content']:
                name = it['variable-name']
                if name in have:
                    prev = name
                    continue
                if not _gated(it):
                    continue
                k = have.index(prev) + 1 if prev else 0
                have.insert(k, name)
                out.insert(k, it)
                prev = name
        return out

    def sequence(self, longest=False, replace=None, **meta):
        replace = replace or {}
        out, dropped = [], []
        for it in self.path(longest=longest, **meta):
            name = it['variable-name']
            if name in replace:
                if replace[name] is not None:
                    out.append(clean(replace[name]))
                continue
            if name in SITE_PAGES:
                continue
            if it.get('is-measured') or narration(it):
                dropped.append(name)
                continue
            out.append(clean(it))
        if dropped:
            print(f'           {self.study} S{self.n}: skipped {len(dropped)} measured/'
                  f'narration item(s): {", ".join(dropped[:5])}'
                  + (' ...' if len(dropped) > 5 else ''))
        return out


class Recon:
    """A v1 battery reconstruction (final/experiment_N.json), for the four listings
    with no revised record."""

    def __init__(self, study, experiment):
        self.ex = json.loads((LEGACY / study / 'final' / f'{experiment}.json').read_text())
        self.items = {}
        for p in self.ex['data']:
            for it in p['study-content']:
                self.items.setdefault(it['variable-name'], it)

    def people(self, **meta):
        return [p for p in self.ex['data']
                if all(p['participant-meta'].get(k) == v for k, v in meta.items())]

    def sequence(self, longest=False, **meta):
        """The modal presentation order of the matching participants, as their items.

        `longest` takes the fullest path instead, for studies whose orders differ
        only because answers hid items."""
        people = self.people(**meta)
        seqs = collections.Counter(_names(p['study-content']) for p in people)
        seq = (max(seqs, key=len) if longest else seqs.most_common(1)[0][0])
        # take each item from a participant on that path, so per-arm text is right
        owner = next(p for p in people if _names(p['study-content']) == seq)
        return [clean(it) for it in owner['study-content']
                if it['variable-name'] not in SITE_PAGES]


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


def authored(name, question, rc, note, **extra):
    return {'type': 'question', 'variable-name': name, 'question': question,
            'response-constraints': rc, 'text_source': 'authored', 'note': note, **extra}


# ---------------------------------------------------------------- per listing
# The four listings with no revised record, unchanged.

def efk28(spec):
    r = Recon('efk28', 'experiment_2')
    arms = []
    for lab in spec['arm_labels']:
        items = r.sequence(case=int(lab['case']), condition=lab['condition'])
        arms.append(upto(items, f"MQ{lab['case']}"))
    return {'arm_blocks': arms}


def sixfjdr(spec):
    r = Recon('6fjdr', 'experiment_1')
    return {'blocks': upto(r.sequence(), 'Impact_vegetarian')}


def sixcxdn(spec):
    r = Recon('6cxdn', 'experiment_2')
    partnered = r.sequence(analysis_relationship_group='partnered')
    single = by_name(r.sequence(analysis_relationship_group='single'))
    head = upto(partnered, 'RoCh.31')
    status = next(it for it in _items(spec['blocks'])
                  if it['variable-name'] == 'relationship_status')
    status = dict(status, note=(
        'Authored. The reconstruction branches on participant-meta.'
        'analysis_relationship_group, which no archive item asks; this question '
        'stands in for it so the branch can be taken.'))
    prqc = dict(by_name(partnered)['PRQC.1'],
                show_if={'variable': 'relationship_status', 'op': '==', 'value': 'Yes'})
    liking = [dict(single[f'liking.{k}'],
                   show_if={'variable': 'relationship_status', 'op': '==', 'value': 'No'})
              for k in (1, 2, 3)]
    return {'blocks': head + [status, prqc] + liking}


def ky9u6(spec):
    r = Recon('ky9u6', 'experiment_1')
    return {'blocks': upto(r.sequence(), 'mhc.14')}


# The eleven listings read from the revised records.

#: The reconstruction keeps the participants' entries out (they were not deposited) and
#: refers to each by a phrase; the entry fields below collect them and the phrase is
#: piped. Field names are the ones already fielded, so collected data line up.
FKRSD_LISTS = {
    'good_habits_typed': ('habit', 'good', 'habit_good_listing'),
    'good_nonhabits_typed': ('nonhabit', 'good', 'good_nonhabit_listing'),
    'bad_habits_typed': ('habit', 'bad', 'habit_bad_listing'),
    'bad_nonhabits_typed': ('nonhabit', 'bad', 'bad_nonhabit_listing'),
}
FKRSD_PHRASE = re.compile(
    r'The (first|second) (habit|behaviour) you listed that (?:is|would be) (good|bad) '
    r'for (the environment|your health)(?: but is not a habit for you)?')
FKRSD_DOMAINS = (('env', 'the environment'), ('health', 'your health'))


def fkrsd(spec):
    r = Record('fkrsd', 3)
    free = {'type': 'free-response', 'single-line': True}
    replace = {name: None for name in FKRSD_LISTS}          # rebuilt as entry pages
    replace.update({
        # Real steps whose prompt the record states; the answers were not deposited.
        'vacation_description': authored(
            'vacation_description',
            'Please describe the vacation you are thinking about in a few short words '
            '(e.g., "beach vacation with family"; "hotel resort stay"; '
            '"backpacking trip").', free,
            'Prompt as the record states it (Materials_Study3.docx); answers not '
            'deposited.'),
        'potential_why': authored(
            'potential_why', 'Why?', {'type': 'free-response'},
            'The record quotes the prompt ("Why?"); answers not deposited.'),
        'comments': authored(
            'comments', 'Do you have any comments?', {'type': 'free-response'},
            'Optional closing box the record describes; wording not deposited.'),
        # Open "why" prompts piped from earlier ratings above/below 50, with no
        # deposited wording; dropped rather than invented.
        'break_reasons': None, 'maintain_start_reasons': None,
    })
    items = upto(r.sequence(longest=True, replace=replace), 'return_home_bad_4')
    out = []
    for it in items:
        out.append(it)
        listing = next((typed for typed, (_, _, lst) in FKRSD_LISTS.items()
                        if lst == it['variable-name']), None)
        if listing is None:
            continue
        kind, val, _ = FKRSD_LISTS[listing]
        fields = []
        for dom, words in FKRSD_DOMAINS:
            for k in (1, 2):
                fields.append(authored(
                    f'{kind}_{dom}_{val}_{k}', f'{val.capitalize()} for {words} ({k})',
                    free, 'Entry field for the slot the reconstruction refers to as '
                          f'"The {("first", "second")[k - 1]} ... you listed that is '
                          f'{val} for {words}"; the entries were not deposited.'))
        out[-1] = {'type': 'page', 'items': [it] + fields}
    for it in out:
        text = it.get('question') or ''
        pipe = {}
        for m in FKRSD_PHRASE.finditer(text):
            k = 1 if m.group(1) == 'first' else 2
            kind = 'habit' if m.group(2) == 'habit' else 'nonhabit'
            dom = 'env' if m.group(4) == 'the environment' else 'health'
            pipe[m.group(0)] = f'{kind}_{dom}_{m.group(3)}_{k}'
        if pipe:
            it['pipe'] = pipe
    fields = {f['variable-name'] for b in out if b.get('type') == 'page'
              for f in b['items']}
    missing = {v for b in out for v in (b.get('pipe') or {}).values()} - fields
    assert not missing, f'fkrsd: piped from uncollected slots {sorted(missing)}'
    return {'blocks': out}


BAGUETTE = authored(
    'baguettecheck',
    'To show that you are reading carefully, please type the word "baguette" in the '
    'box below.', {'type': 'free-response', 'single-line': True},
    'The record has the check (every analysed person typed "baguette") but not its '
    'instruction; this wording stands in for it.', check='instructed')


def ninebhq_s1(spec):
    r = Record('9ebhq', 1)
    items = upto(r.sequence(replace={'baguettecheck': BAGUETTE}), 'proven.CTS5.')
    n = [it['variable-name'] for it in items]
    a, b = n.index('informed_instructions'), n.index('proven_instructions')
    c = n.index('proven.CTS5.') + 1
    # "order of perceived-knowledge and proven/disproven scales was randomized"
    return {'blocks': items[:a] + [shuffle([seq(*items[a:b]), seq(*items[b:c])])]
            + items[c:], 'target': 'f06'}


def ninebhq_s2(spec):
    r = Record('9ebhq', 2)
    return {'blocks': upto(r.sequence(replace={'baguettecheck': BAGUETTE}),
                           'informed.MU3.')}


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
    r = Record('hvdwk', 2)
    # "Item order within each scale was randomized per participant"; the instructed
    # check CR_efficacy_9 sits inside its scale and is shuffled with it
    return {'blocks': shuffle_scales(upto(r.sequence(), 'worry_'), HVDWK_SCALES),
            'target': 'f19'}


def hvdwk_s3(spec):
    r = Record('hvdwk', 3)
    return {'blocks': shuffle_scales(upto(r.sequence(), 'worry_'), HVDWK_SCALES)}


def aj5mt(spec):
    r = Record('aj5mt', 1)
    decks = sorted({p['participant-meta']['counterbalanced_condition'] for p in r.data})
    return {'arms': len(decks), 'arm_keys': ['deck'],
            'arm_labels': [{'deck': str(d)} for d in decks],
            'arm_blocks': [upto(r.sequence(counterbalanced_condition=d), '18_C1_4')
                           for d in decks]}


def ba65f_a(spec):
    r = Record('ba65f', 1)
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


def ba65f_b(spec):
    """Each of the ten situations is shown with ONE helping action, and every Group B
    participant saw exactly five high-cost and five low-cost actions. The `balanced`
    block draws the situation order and then alternates the level across it, which
    keeps that 5/5 split; independent draws would not. The variants and their item
    order are the record's."""
    r = Record('ba65f', 1)
    rx = re.compile(r'([A-Za-z]+)_(Low|High)_vignette')
    cells = collections.OrderedDict()
    head = []
    people = r.people(group='B')
    for p in people:
        cur = None
        for it in p['study-content']:
            m = rx.fullmatch(it['variable-name'])
            if m:
                cur = (m.group(1), m.group(2))
                cells.setdefault(cur[0], collections.OrderedDict()).setdefault(cur[1], [])
            if cur is None:
                if p is people[0]:
                    head.append(it)
                continue
            got = cells[cur[0]][cur[1]]
            # a cell is its vignette and the questions named after it; what follows
            # the last one (the debrief) is not part of it
            if not (it['variable-name'] == f'{cur[0]}_{cur[1]}_vignette' or
                    it['variable-name'].startswith(f'{cur[0].lower()}_{cur[1][0].lower()}_')):
                continue
            if it['variable-name'] not in [x['variable-name'] for x in got]:
                got.append(it)
    head = [clean(it) for it in head
            if it['variable-name'] not in SITE_PAGES and not narration(it)]
    for sit, levels in cells.items():
        assert set(levels) == {'Low', 'High'}, f'ba65f_B: {sit} has {set(levels)}'
    block = {'type': 'balanced', 'items': [
        {'type': 'group', 'cell': sit, 'items': [
            {'type': 'group', 'shuffle': False, 'level': lev,
             'items': [clean(it) for it in levels[lev]]}
            for lev in ('Low', 'High')]}
        for sit, levels in cells.items()]}
    return {'blocks': head + [block]}


#: The block instructions the reconstruction has no deposited wording for; the v1
#: reconstruction's instruction is kept instead of the record's narration.
DQSV6_INSTRUCTIONS = ('globalism_instructions', 'rwa_instructions', 'sdo_instructions')


def dqsv6(spec):
    r = Record('dqsv6', 1)
    replace = {name: {'type': 'stimuli', 'variable-name': name,
                      'content': 'Please indicate how much you agree with the '
                                 'following statements.',
                      'text_source': 'paraphrased',
                      'note': 'v1 reconstruction wording; the block instruction is '
                              'not deposited.'}
               for name in DQSV6_INSTRUCTIONS}
    items = r.sequence(replace=replace)
    # "items in each measure were presented in random order"
    scales = {rx: one for rx in (r'ID\d', r'CN\d', r'(Anarch|Pacyf)\d', r'Glob\d',
                                 r'RWA\d', r'SDO\d')}
    return {'blocks': shuffle_scales(upto(items, 'politicalconservatism'), scales)}


def kf4e6(spec):
    r = Record('kf4e6', 1)
    arms = []
    for lab in spec['arm_labels']:
        code = {'conjunctive': 'C', 'disjunctive': 'D'}[lab['causal_structure']] + '_' + \
            {'action': 'A', 'inaction': 'I'}[lab['action_type']]
        items = upto(r.sequence(condition_code=code), f'{code}_1')
        n = [it['variable-name'] for it in items]
        a, b = n.index(f'{code}_vignette'), n.index(f'{code}_1')
        assert b == a + 1, f'kf4e6 {code}: vignette and rating not adjacent'
        # "one causal-agreement rating shown on the same page as the vignette"
        arms.append(items[:a] + [{'type': 'page', 'items': items[a:b + 1]}] + items[b + 1:])
    return {'arm_blocks': arms}


FXP7G_CONDS = ['control', 'manipulated_goal', 'measured_goal', 'measured_site_preference']


def _fxp7g_matrix(r, rows, lead=()):
    """One Qualtrics matrix as one page: the record's template is a shared stem plus
    the row's {headline}, so the stem is shown once and the headlines are the rows,
    in random order ("headline order randomized")."""
    tpl = r.items[rows[0]['variable-name']]['template']
    stem = tpl.split('{headline}')[0].rstrip()
    out = []
    for it in rows:
        assert r.items[it['variable-name']]['template'] == tpl, 'fxp7g: mixed matrix'
        assert it['question'].startswith(stem), f"fxp7g: {it['variable-name']} off-stem"
        out.append(dict(it, question=it['question'][len(stem):].strip()))
    stim = {'type': 'stimuli', 'variable-name': rows[0]['variable-name'].rsplit('_h', 1)[0]
            + '_stem', 'content': stem, 'text_source': rows[0].get('text_source')}
    return {'type': 'page', 'shuffle': True, 'items': list(lead) + [stim] + out}


def _fxp7g_layout(r, items):
    """(head, ratings page, rest). The ratings are one matrix page, with the
    instructions the stem says are "added above (in grey)" on it; then one matrix page
    per IMI statement, each over the eight headlines."""
    n = [it['variable-name'] for it in items]
    rate = [i for i, x in enumerate(n) if x.startswith('likelihood_sentiment_h')]
    imi = [i for i, x in enumerate(n) if re.fullmatch(r'IMI_\d+_h\d+', x)]
    assert rate == list(range(rate[0], rate[-1] + 1)), 'fxp7g: ratings not contiguous'
    assert imi == list(range(imi[0], imi[-1] + 1)), 'fxp7g: IMI block not contiguous'
    cut = rate[0] - 1 if n[rate[0] - 1].endswith('_repeated') else rate[0]
    statements = collections.OrderedDict()
    for i in imi:
        statements.setdefault(n[i].split('_h')[0], []).append(items[i])
    page = _fxp7g_matrix(r, items[rate[0]:rate[-1] + 1], items[cut:rate[0]])
    return (items[:cut], page, items[rate[-1] + 1:imi[0]]
            + [_fxp7g_matrix(r, rows) for rows in statements.values()] + items[imi[-1] + 1:])


def fxp7g(spec):
    """Four conditions x two headline sets. Within manipulated_goal the record assigns
    a credibility or an enjoyment goal (about half each); the arm draws one of the two
    framings at random, so the condition keeps its share of the sample."""
    r = Record('fxp7g', 4)
    labels, arms = [], []
    for c in FXP7G_CONDS:
        for s in (1, 2):
            if c == 'manipulated_goal':
                variants = [_fxp7g_layout(r, r.sequence(condition=c, set=s,
                                                        goal_orientation=g))
                            for g in ('credibility', 'enjoyment')]
                heads = [v[0] for v in variants]
                rest = variants[0][2]
                assert json.dumps(variants[1][2]) == json.dumps(rest), \
                    'fxp7g: goal framings differ beyond the framing pages'
                common = 0
                while (common < min(map(len, heads)) and
                       heads[0][common]['variable-name'] == heads[1][common]['variable-name']):
                    common += 1
                blocks = heads[0][:common] + [shuffle(
                    [seq(*h[common:], v[1]) for h, v in zip(heads, variants)], pick=1)] + rest
            else:
                head, page, rest = _fxp7g_layout(r, r.sequence(condition=c, set=s))
                blocks = head + [page] + rest
            labels.append({'condition': c, 'set': str(s)})
            arms.append(blocks)
    return {'arms': len(arms), 'arm_keys': ['condition', 'set'], 'arm_labels': labels,
            'arm_blocks': arms}


#: The three attention statements the record knows the wording of (from the QSF) but
#: stores only as narration, because only pass/fail flags were deposited.
KXCWM_CHECKS = {
    'temps_attention_statement': ('temps_att_check', 'idiff_temps_1',
                                  'I have to swim the Atlantic Ocean every morning to '
                                  'get to work.'),
    'hps_attention_statement_1': ('hps_att_check_1', 'idiff_hps_1',
                                  'I bought tickets for a trip to the moon this summer.'),
    'hps_attention_statement_2': ('hps_att_check_2', 'idiff_hps_1',
                                  'I have a dinosaur as a pet at home.'),
}


def kxcwm(spec):
    """Two creativity tasks (object uses, unusual consequences), counterbalanced; two
    of eight prompts per task, drawn at random. Each prompt is a two-minute
    timed-ideas page with up to 15 ideas (the record's maximum), then its
    time's-up page, difficulty and self-rated originality, in the record's order."""
    r = Record('kxcwm', 1)
    old = {}
    for it in _items(spec.get('arm_blocks') or spec['blocks']):
        if it['type'] == 'timed-ideas':
            old.setdefault(it['variable-name'], it)
    replace = {name: {'type': 'question', 'variable-name': var,
                      'question': text, 'check': 'instructed', 'text_source': 'qsf',
                      'response-constraints': r.items[like]['response-constraints'],
                      'note': 'Wording from qualtrics_experiment.qsf, as the record '
                              'cites it; only pass/fail flags were deposited.'}
               for name, (var, like, text) in KXCWM_CHECKS.items()}

    def task(t):
        runs = []
        for name in sorted(r.items):
            m = re.fullmatch(rf'prompt_{t}_(\w+)', name)
            if not m:
                continue
            p = f'{t}_{m.group(1)}'
            prompt = r.items[name]
            timed = dict(old.get(f'idea_{p}', {}), type='timed-ideas',
                         **{'variable-name': f'idea_{p}'})
            timed.update(question=prompt['content'], text_source=prompt['text-source'],
                         n_fields=15, duration_ms=120000)
            runs.append(seq(timed, *(clean(r.items[f'{k}_{p}'])
                                     for k in ('timeup', 'cogload', 'selfeval'))))
        assert len(runs) == 8, f'kxcwm: {len(runs)} {t} prompts'
        # "4 prompts drawn at random from 16": two per task
        return [clean(r.items[f'instructions_{t}']), shuffle(runs, pick=2)]

    arms = []
    for order in ('aut_ct', 'ct_aut'):
        rest = r.sequence(longest=True, replace=replace, task_order_condition=order)
        names = [it['variable-name'] for it in rest]
        tail = upto(rest[names.index('csb_instructions'):], 'idiff_hps_48')
        first, second = order.split('_')
        # "order of Alternate Uses vs Consequences task blocks counterbalanced"
        arms.append([clean(r.items['intro_creativity_tasks'])] + task(first)
                    + [clean(r.items['halfway_slide'])] + task(second) + tail)
    return {'arms': 2, 'arm_keys': ['task_order_condition'],
            'arm_labels': [{'task_order_condition': 'aut_ct'},
                           {'task_order_condition': 'ct_aut'}],
            'arm_blocks': arms}


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
    """Three scenario conditions; one rating to the outcome, the full instrument with
    --full, laid out as the Qualtrics instrument was fielded (`kfrux_as_fielded`)."""
    r = Record('kfrux', 1)
    labs = [l['condition'] for l in spec['arm_labels']]
    drop = {'authenticity_items': None}
    if not FULL:
        return {'arm_blocks': [upto(r.sequence(condition=c, replace=drop), 'creativity')
                               for c in labs]}
    return {'arm_blocks': [kfrux_as_fielded(r.sequence(condition=c, longest=True,
                                                       replace=drop), c)
                           for c in labs]}


#: Exceptions to rule 3 and 4 for kfrux, each restoring what the original Qualtrics
#: instrument shows (prolific_battery_v1/studies/kfrux/raw/data_a78gz/Study Materials/
#: Qualtrics/Study 1A.docx) and the reconstruction lost:
#:   - the timing words are capitalised there ("at the BEGINNING" / "at the END");
#:   - each Qualtrics block is one page: scenario + creativity + effort (block
#:     "creativity"), the consequence lead-in + con1 + con2 + price (block
#:     "consequence"), and feedback + the attention check (block "funnel").
#: The authenticity block is left out: the record keeps it only as narration (the
#: deposit has no responses to it for any row), and the paper does not report it.
KFRUX_CAPS = (('at the beginning of', 'at the BEGINNING of'),
              ('at the end of', 'at the END of'))
KFRUX_PAGES = (('intro',), ('scenario', 'creativity', 'effort'),
               ('consequence_intro', 'con1', 'con2', 'price'), ('feedback', 'ac'))


def kfrux_as_fielded(items, condition):
    items = copy.deepcopy(items)
    scenario = f'scenario_{condition}'
    for it in items:
        if it['variable-name'] == scenario:
            for old, new in KFRUX_CAPS:
                it['content'] = it['content'].replace(old, new)
    named = by_name(items)
    named['scenario'] = named.pop(scenario)
    paged = [n for page in KFRUX_PAGES for n in page]
    missing = [n for n in paged if n not in named]
    extra = [n for n in named if n not in paged]
    if missing or extra:
        raise SystemExit(f'kfrux: page layout out of step with the reconstruction '
                         f'(missing {missing}, unplaced {extra})')
    return [{'type': 'page', 'items': [named[n] for n in page]} for page in KFRUX_PAGES]


def cse5r(spec):
    """Representation-goals vs control; the nomination task then its ratings. The
    record gates the five organisation follow-ups on `initiative` == "Yes"; full scope
    fields them behind that gate rather than fielding either branch unconditionally."""
    r = Record('cse5r', 1)
    labs = [l['condition'] for l in spec['arm_labels']]
    return {'arm_blocks': [upto(r.sequence(condition=c, longest=FULL), 'asn_womn')
                           for c in labs]}


LISTINGS = {
    'kfrux': kfrux, 'cse5r': cse5r, 'efk28': efk28, 'fkrsd': fkrsd, '6fjdr': sixfjdr,
    '6cxdn': sixcxdn, '9ebhq_S1': ninebhq_s1, '9ebhq_S2': ninebhq_s2,
    'hvdwk_S2': hvdwk_s2, 'hvdwk_S3': hvdwk_s3, 'aj5mt': aj5mt, 'ba65f_A': ba65f_a,
    'ba65f_B': ba65f_b, 'dqsv6': dqsv6, 'ky9u6': ky9u6, 'kf4e6': kf4e6, 'fxp7g': fxp7g,
    'kxcwm': kxcwm,
}

#: Targets moved by the revised findings: the deployed one was demoted to secondary
#: (cse5r f04, kxcwm f65) or changed meaning (ba65f f16). The replacement is the main,
#: scored finding in the SAME archive study, so no listing changes experiment.
TARGETS = {'cse5r': 'f24', 'kxcwm': 'f85', 'ba65f_A': 'f09', 'ba65f_B': 'f09'}


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


def main():
    global FULL
    check = '--check' in sys.argv
    FULL = '--full' in sys.argv
    only = [a for a in sys.argv[1:] if a in LISTINGS]
    for name, build in LISTINGS.items():
        if only and name not in only:
            continue
        old = _load(name)
        new = copy.deepcopy(old)
        for k in ('blocks', 'arms', 'arm_keys', 'arm_labels', 'arm_blocks'):
            new.pop(k, None)
        new.update(build(old))
        new['target'] = TARGETS.get(name, new['target'])
        if 'arm_blocks' in new and 'arms' not in new:
            new['arms'] = old['arms']
            new['arm_keys'], new['arm_labels'] = old['arm_keys'], old['arm_labels']
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
        if not check:
            (SITE / name / 'spec.json').write_text(
                json.dumps(new, indent=1, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
