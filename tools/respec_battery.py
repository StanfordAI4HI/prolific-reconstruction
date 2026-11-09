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

Records. All fifteen studies are read from the revised `ba/3` records (data1030:
`<id>/data/study_N.json`; efk28, 6fjdr, 6cxdn and ky9u6 came in the second batch,
prolific_4_records.zip). From a ba/3 record this script

- takes only people the record does not flag in `participant-meta.excluded` when
  choosing a path (the revision restored excluded people as flagged rows);
- does not ask items marked `is-measured`. A response time (aj5mt's `<n>_L1rt`) is
  tagged onto the question it times as `rt_as`, and ingest writes it, in seconds, from
  that answer's `rt_ms`; any other measured item is skipped;
- skips the reconstruction's narration — `synthesized` stimuli written in the second
  person ("You type your four good habits into four boxes...") that describe a step
  whose material was not deposited. They are not something a participant can be
  shown. A listing replaces one with a real item only where the record gives the
  wording (kxcwm's attention statements) or the step is a plain entry box (fkrsd), and
  marks the replacement `authored` or with its source;
- turns `shown-if` on an earlier answer into the renderer's `show_if`; a `shown-if` on
  an assignment is what the arm (or a random pick inside it) already decides.

The reconstructions are read from --records PATH (or $BA_RECORDS, or
../../data1030/records beside the deploy checkout).

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


RECORDS = _arg('--records', 'BA_RECORDS', SITE.parent.parent / 'data1030' / 'records')

KEEP = ('type', 'variable-name', 'question', 'content', 'response-constraints',
        'text_source', 'condition', 'check')
# Pages the site supplies itself (consent is spec['consent']; there is no debrief page).
SITE_PAGES = {'consent', 'consent_intro', 'consent_information', 'IC', 'Q17', 'debrief',
              'Informed_consent', 'Consent'}
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
    for k in ('show_if', 'pipe', 'note', 'rt_as'):  # set by a listing or by sequence()
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
            if it.get('is-measured') and re.search(r'(rt|_time)$', name, re.I) \
                    and out and out[-1]['type'] == 'question':
                # a response time is measured on the question it follows: ingest
                # writes it as this item, in seconds, from that answer's rt_ms
                out[-1]['rt_as'] = name
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
# The four listings added in the second revised batch (prolific_4_records.zip).

def efk28(spec):
    """Study 2: six arms (three life stories x impact ending). The revised record adds
    the per-story lead-in, the attention item `Q1_20` ("He was a rockstar.", the
    check the authors excluded 83 people on) and the closing religiosity and
    politics questions."""
    r = Record('efk28', 2)
    arms = []
    for lab in spec['arm_labels']:
        items = r.sequence(case=int(lab['case']), condition=lab['condition'])
        arms.append(upto(items, f"MQ{lab['case']}"))
    return {'arm_blocks': arms}


#: 6fjdr's Study 1 survey PDF (deposit rdy2v, Survey/Study 1_survey.pdf) holds what the
#: record dropped or flattened: the attention check's wording and options, every scale
#: point's label, and the grids the items were asked in. Taken verbatim from it.
SIXFJDR_ATTENTION = authored(
    'attention_check',
    'For this question, to show that you have read these instructions carefully, '
    'please select all five of the answers below.',
    {'type': 'mcq', 'options': ['Extremely important', 'Very important',
                                'Somewhat important', 'Only a little important',
                                'Not at all important'], 'max-choices': 5},
    'Verbatim from the Study 1 survey PDF, where it follows the Prolific ID. The '
    'record keeps only a summary of this step (all analysed people passed). Passing '
    'means selecting all five; the original ended a failing session, ours excludes '
    'it at ingest.', check='attention')
SIXFJDR_ATTENTION['text_source'] = 'survey_pdf'
SIXFJDR_AGREE = ['Strongly disagree', 'Somewhat disagree', 'Neither agree nor disagree',
                 'Somewhat agree', 'Strongly agree']
SIXFJDR_LABELS = (
    (r'persact_(vegan|vegetarian|eatseasonal|energyefficappl|lessfoodwaste|buyless|'
     r'recycle|avoidflights|lowertemp|carpool)',
     ['Never', 'Rarely', 'Sometimes', 'Most of the time', 'Always']),
    (r'Impact_.*', ['Small', 'Moderate', 'Large']),
    (r'misinformation2|mot_re_.*|heu_.*', SIXFJDR_AGREE),
    (r'politics', ['Left', '', '', 'Center', '', '', 'Right']),
)
#: The survey's grids, one page each: (first row, last row, stem). A stem of None is the
#: record's own instruction item just before the first row; otherwise the PDF's stem.
SIXFJDR_GRIDS = (
    ('persact_vegan', 'persact_carpool', None),
    ('persact_owncar', 'persact_renewelec', 'Please answer the following questions.'),
    ('Impact_buyless', 'Impact_vegetarian', None),
    ('mot_re_convenience', 'mot_re_persvalues',
     'Please indicate the extent to which you agree or disagree with these statements:'),
    ('heu_balance1', 'heu_balance2',
     'To what extent do you agree or disagree with the following statements?'),
    ('conflation_heatingcooling', 'conflation_airpoll', None),
)


def sixfjdr(spec):
    """Study 1, laid out as its survey PDF: the attention check after consent, every
    scale point labelled, and each grid of the PDF on one page with the action (or
    statement) as the row, in the PDF's row order (the deposit records no
    randomisation). The carbon-numeracy estimates are number boxes (kg)."""
    r = Record('6fjdr', 1)
    items = upto(r.sequence(replace={'prolific_attention_check': SIXFJDR_ATTENTION}),
                 'Impact_vegetarian')
    for it in items:
        for rx, labels in SIXFJDR_LABELS:
            if re.fullmatch(rx, it['variable-name']):
                rc = it['response-constraints']
                assert rc['scale-max'] - rc['scale-min'] + 1 == len(labels), it['variable-name']
                rc['scale-labels'] = labels
    names = [it['variable-name'] for it in items]
    out, i = [], 0
    starts = {g[0]: g for g in SIXFJDR_GRIDS}
    while i < len(items):
        g = starts.get(names[i])
        if g is None:
            out.append(items[i])
            i += 1
            continue
        j = names.index(g[1]) + 1
        if g[2] is None:
            stem = out.pop()
            assert stem['type'] == 'stimuli', f'6fjdr: no stem before {g[0]}'
        else:
            stem = {'type': 'stimuli', 'variable-name': f'{g[0]}_stem', 'content': g[2],
                    'text_source': 'survey_pdf',
                    'note': 'The grid stem, verbatim from the Study 1 survey PDF.'}
        rows = []
        for it in items[i:j]:
            q = it['question']
            # the record turned each grid row into "<stem> — <row>"; the stem is on
            # the page, so the row keeps only its own label
            rows.append(dict(it, question=q.split(' \u2014 ', 1)[1]) if ' \u2014 ' in q else it)
        out.append({'type': 'page', 'shuffle': False, 'items': [stem] + rows})
        i = j
    return {'blocks': out}


#: 6cxdn branches on participant-info.relationship_status, which the original took
#: from its screener rather than asking in the survey. The question below asks it and
#: writes it to participant-info under the record's own values.
SIXCXDN_STATUS = {
    'Yes, I am in a romantic relationship': 'in a romantic relationship',
    'No, I am single, and there is someone I have a romantic interest in or have '
    'recently dated': 'single with a current romantic interest',
}


def _merge(a, b):
    """Items of path `a`, with those only in path `b` inserted after the item that
    precedes them in `b` (the two branches of one instrument)."""
    out = list(a)
    have = [it['variable-name'] for it in out]
    prev = None
    for it in b:
        name = it['variable-name']
        if name not in have:
            k = have.index(prev) + 1 if prev else 0
            have.insert(k, name)
            out.insert(k, it)
        prev = name
    return out


def sixcxdn(spec):
    """Study 3 (record study 2): one instrument with a partnered and a single branch.
    The authored status question takes the branch; the record's instructed-response
    item `ac1` keeps its place and answer (2, chosen by 1,110 of 1,113) with authored
    wording, as its own was not deposited."""
    r = Record('6cxdn', 2)
    label = {v: k for k, v in SIXCXDN_STATUS.items()}
    ac1 = authored('ac1', 'For this line, please select 2.',
                   r.items['ac1']['response-constraints'],
                   'Authored. The record keeps this instructed-response check (answer 2) '
                   'without its wording.', check='instructed')
    paths = [r.sequence(analysis_relationship_group=g, replace={'ac1': ac1})
             for g in ('partnered', 'single')]
    items = _merge(*paths)
    for it in items:
        crit = (r.items.get(it['variable-name'], {}).get('shown-if') or {}).get('criteria', [])
        gate = [c for c in crit if c.get('field') == 'participant-info.relationship_status']
        if gate:
            it['show_if'] = {'variable': 'relationship_status', 'op': '==',
                             'value': label[gate[0]['value']]}
    status = demo('relationship_status', 'Are you currently in a romantic relationship?',
                  SIXCXDN_STATUS, name='relationship_status')
    status['note'] = ('Authored. The record branches on participant-info.'
                      'relationship_status, which the original took from its screener; '
                      'the options are the values it records.')
    return {'blocks': [status] + upto(items, 'RoCh.31')}


#: ky9u6's HEMA-R block names each project the participant wrote (`pp.1`-`pp.3`).
KY9U6_PROJECT = '(the project you wrote as #{k})'


def ky9u6(spec):
    r = Record('ky9u6', 1)
    items = r.sequence()
    for it in items:
        m = re.fullmatch(r'hema_project_(\d)', it['variable-name'])
        if m:
            k = m.group(1)
            slot = KY9U6_PROJECT.format(k=k)
            it['content'] = r.items[it['variable-name']]['template'].replace(
                f'{{project_{k}}}', slot)
            it['pipe'] = {slot: f'pp.{k}'}
    return {'blocks': upto(items, 'mhc.14')}


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


#: The original's perceived-knowledge grid labelled every column; its instructions
#: (OSF dazqb, "Scales used in the three studies") define these five. Labelled only at
#: its ends, the first 15 Study 2 participants rated the made-up theories well above
#: the original (2.31 vs 1.53), so from 2026-11-01 every point carries its label.
#: Study 1 was fielded with the ends only and is left as fielded.
INFORMED_LABELS = ['Not at all informed', 'Minimally informed', 'Somewhat informed',
                   'Well informed', 'Extremely informed']


def ninebhq_s2(spec):
    r = Record('9ebhq', 2)
    items = upto(r.sequence(replace={'baguettecheck': BAGUETTE}), 'informed.MU3.')
    for it in items:
        if it.get('variable-name', '').startswith('informed.'):
            it['response-constraints']['scale-labels'] = INFORMED_LABELS
    return {'blocks': items}


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


#: Education options differ between the two studies' instruments.
HVDWK_EDUCATION = {
    2: ['Primary school', 'Secondary School', "Bachelor's degree", "Master's degree",
        'Doctoral degree'],
    3: ['Secondary school or lower', "Bachelor's degree or equivalent",
        "Master's degree or higher"],
}


def hvdwk_demographics(n):
    """Age, gender, income and education, asked just before political_1 as in the
    original survey (codebook_study{2,3}.xlsx). The record keeps them only as
    participant-info, so respec would otherwise never field them, yet the paper's
    Table 3 correlations, every listwise sample built on it and the Table 5-7
    regressions all control for them. Each carries `to_info`, which ingest uses to
    write the answer into participant-info under the name and spelling the measures
    read."""
    src = f'codebook_study{n}.xlsx'
    income = ['Less than 20,000 pounds', '20,000-39,999 pounds', '40,000-59,999 pounds',
              '60,000-99,999 pounds', 'More than 100,000 pounds']
    return [
        demo('age', 'Please state your age in full years.', None, name='age', src=src),
        demo('gender', 'What gender do you identify with?',
             {'Male': 'male', 'Female': 'female', 'Other': 'other',
              'Prefer not to say': 'prefer not to say'}, name='Gender', src=src),
        demo('income', 'Gross annual household income in British Pounds',
             {o: o for o in income}, name='income', src=src),
        demo('education', 'Please indicate your highest completed level of education.',
             {o: o for o in HVDWK_EDUCATION[n]}, name='education', src=src),
    ]


def _hvdwk(n):
    items = upto(Record('hvdwk', n).sequence(), 'worry_')
    k = [it['variable-name'] for it in items].index('political_1')
    # "Item order within each scale was randomized per participant"; the instructed
    # check CR_efficacy_9 sits inside its scale and is shuffled with it
    return shuffle_scales(items[:k] + hvdwk_demographics(n) + items[k:], HVDWK_SCALES)


def hvdwk_s2(spec):
    return {'blocks': _hvdwk(2), 'target': 'f19'}


def hvdwk_s3(spec):
    return {'blocks': _hvdwk(3)}


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


FXP7G_SHUFFLED = ('mindset_measure', 'characteristic_measure')
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
    # Every "_repeated" reminder belongs on the ratings page. In the measured arms
    # there is one per answer, each gated on it, so all of them go there (only the
    # participant's own is shown); taking only the one adjacent to the ratings left
    # the other branch's reminder on a page of its own and its ratings without it.
    head = [it for it in items[:rate[0]] if not n[items.index(it)].endswith('_repeated')]
    lead = [it for it in items[:rate[0]] if n[items.index(it)].endswith('_repeated')]
    statements = collections.OrderedDict()
    for i in imi:
        statements.setdefault(n[i].split('_h')[0], []).append(items[i])
    page = _fxp7g_matrix(r, items[rate[0]:rate[-1] + 1], lead)
    return (head, page, items[rate[-1] + 1:imi[0]]
            + [_fxp7g_matrix(r, rows) for rows in statements.values()] + items[imi[-1] + 1:])


def fxp7g(spec):
    """Four conditions x two headline sets. Within manipulated_goal the original
    randomized a credibility or an enjoyment goal (Qualtrics' `credibility` field,
    about half each). That goal is the measures' `goal_orientation`, and it is shown
    only as a stimulus, which the payload does not carry, so it is made part of the
    arm: ingest copies an arm's labels into participant-meta. To keep the original's
    equal split over the four conditions, each of the other conditions' arms appears
    twice, so every condition x set is 2 of the 16 arms and each goal 1 of them."""
    r = Record('fxp7g', 4)
    labels, arms = [], []
    for c in FXP7G_CONDS:
        for s in (1, 2):
            if c == 'manipulated_goal':
                for g in ('credibility', 'enjoyment'):
                    head, page, rest = _fxp7g_layout(
                        r, r.sequence(condition=c, set=s, goal_orientation=g))
                    labels.append({'condition': c, 'set': str(s), 'goal_orientation': g})
                    arms.append(head + [page] + rest)
            else:
                head, page, rest = _fxp7g_layout(r, r.sequence(condition=c, set=s))
                for _ in range(2):
                    labels.append({'condition': c, 'set': str(s)})
                    arms.append(head + [page] + rest)
    # As the Qualtrics file has them (Heterogeneity_-_..._Sentiment_Mechanism.qsf):
    # the two goal measures (Q37, Q63) randomize the order of their two answers, and
    # the attention check (Q113) asks for "yes" typed in its "Other" box.
    for arm in arms:
        for it in _items(arm):
            if it['variable-name'] in FXP7G_SHUFFLED:
                it['shuffle_options'] = True
            if it['variable-name'] == 'attention':
                it['other_text'] = 'Other (please specify)'
    return {'arms': len(arms), 'arm_keys': ['condition', 'set', 'goal_orientation'],
            'arm_labels': labels, 'arm_blocks': arms}


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
    return {'arm_blocks': [cse5r_ranking(upto(r.sequence(condition=c, longest=FULL),
                                              'asn_womn'))
                           for c in labs]}


#: The goals were ranked in Qualtrics by drag and drop, so every participant's three
#: ranks are distinct (all 985 analysed are a permutation of 1-2-3). The record stores
#: them as three single-choice items; asked that way a participant could give 1, 1, 1.
#: They are fielded as one ranking page instead (render.js `rank`): the shared
#: instruction once, a row per goal, and a rank can go to only one row. The three
#: variables and their "1"/"2"/"3" answers are unchanged, so measures and ingest are.
CSE5R_RANKS = ('gl_rank_0_1_RANK', 'gl_rank_0_2_RANK', 'gl_rank_0_3_RANK')
CSE5R_RANK_SPLIT = '\nRank you gave to: '


def cse5r_ranking(items):
    n = [it['variable-name'] for it in items]
    if CSE5R_RANKS[0] not in n:
        return items                       # outcome-only scope stops before them
    a = n.index(CSE5R_RANKS[0])
    assert tuple(n[a:a + 3]) == CSE5R_RANKS, f'cse5r: rank items not contiguous {n[a:a + 3]}'
    stems = {it['question'].split(CSE5R_RANK_SPLIT)[0] for it in items[a:a + 3]}
    assert len(stems) == 1 and all(CSE5R_RANK_SPLIT in it['question']
                                   for it in items[a:a + 3]), 'cse5r: rank stems differ'
    rows = [dict(it, question=it['question'].split(CSE5R_RANK_SPLIT)[1])
            for it in items[a:a + 3]]
    stem = {'type': 'stimuli', 'variable-name': 'gl_rank_stem', 'content': stems.pop(),
            'text_source': items[a].get('text_source')}
    page = {'type': 'page', 'rank': True, 'items': [stem] + rows,
            'rank_note': '1 = most important, 3 = least important. Each rank can be '
                         'given to only one goal.',
            'note': 'Layout restored: a drag-and-drop ranking in the original. The note '
                    'is authored (the record codes 1 as most important).'}
    return items[:a] + [page] + items[a + 3:]



# ---------------------------------------------------------------- demographics
#: A finding may read participant-info (age, gender, education, ...). The records keep
#: those as the person's background, not as items, so nothing above fields them; each
#: listing below asks them as questions instead, and nothing is taken from Prolific's
#: export. `to_info` tells ingest where an answer goes: participant-info[key], through
#: `map` (option shown -> the record's own value, the spelling the measures compare
#: against) or `format` (a number into the record's string). Fields, values and which
#: findings need them: scratchpad info_dependence.py, run over every record.


def demo(key, question, values, name=None, multi=False, src='authored', fmt=None,
         scale=None):
    if values is None and scale is None:
        rc = {'type': 'scalar', 'scale-min': 18, 'open': True}
        to = {'key': key}
    elif scale is not None:
        rc = dict({'type': 'scalar'}, **scale)
        to = {'key': key, 'format': fmt}
    else:
        rc = {'type': 'mcq', 'options': list(values), 'max-choices': len(values) if multi else 1}
        to = {'key': key, 'map': dict(values)}
    it = {'type': 'question', 'variable-name': name or f'demo_{key}', 'question': question,
          'response-constraints': rc, 'text_source': src, 'to_info': to}
    if src == 'authored':
        it['note'] = ('Authored: the record keeps this only as participant-info, without '
                      'its wording; the options are the values it records.')
    return it


AGE = 'What is your age (in years)?'
GENDER = 'What is your gender?'

#: listing -> (where, questions). `start` where the record places the original
#: demographics before the study (9ebhq: the opening sociodemographics block; fkrsd:
#: the demographics step right after consent), `end` otherwise.
DEMOGRAPHICS = {
    '9ebhq_S1': ('start', [
        demo('age', AGE, None),
        demo('gender', GENDER + ' (select all that apply)',
             {'Female': 'female', 'Male': 'male', 'Non-binary / other': 'non-binary/other'},
             multi=True)]),
    '9ebhq_S2': ('start', [
        demo('age', AGE, None),
        demo('gender', GENDER + ' (select all that apply)',
             {'Female': 'female', 'Male': 'male', 'Non-binary / other': 'non-binary/other'},
             multi=True),
        # The original ticked one of five labelled boxes (OSF dazqb, `educ.1.`-`educ.5.`,
        # coded 1-5 by the box). Only the end labels are published; the middle three are
        # reconstructed to fit its distribution (2% / 37% / 42% / 18% on 2-5). A 1-5
        # scale with only the ends labelled sent bachelor's holders to 5.
        demo('education', 'What is the highest degree you have obtained?',
             {'No formal education': '1 of 5 (no formal education)',
              'Primary / middle school': '2 of 5 (primary / middle school)',
              'High school': '3 of 5 (high school)',
              'College degree (undergraduate)': '4 of 5 (college degree, undergraduate)',
              'Graduate degree': '5 of 5 (graduate degree)'})]),
    'aj5mt': ('end', [demo('age', AGE, None),
                      demo('gender', GENDER, {'Female': 'female', 'Male': 'male'})]),
    'ba65f_A': ('end', [demo('age', AGE, None),
                        demo('gender', GENDER, {'Female': 'female', 'Male': 'male',
                                                'Non-binary': 'non-binary'})]),
    'ba65f_B': ('end', [demo('age', AGE, None),
                        demo('gender', GENDER, {'Female': 'female', 'Male': 'male',
                                                'Non-binary': 'non-binary'})]),
    'cse5r': ('end', [demo('age', AGE, None),
                      demo('gender', GENDER, {'Female': 'Female', 'Male': 'Male',
                                              'Other / non-binary': 'Other/Nonbinary'})]),
    'dqsv6': ('end', [demo('age', AGE, None),
                      demo('gender', GENDER, {'Woman': 'woman', 'Man': 'man',
                                              'Non-binary': 'non-binary'})]),
    'fkrsd': ('start', [
        demo('age', AGE, None),
        demo('gender', GENDER, {o: o for o in ('Female', 'Male', 'Non-binary / third gender',
                                               'Prefer not to say')}),
        demo('country', 'In which country do you currently live?',
             {'United States': 'United States of America', 'Canada': 'Canada',
              'Australia': 'Australia',
              'United Kingdom': 'United Kingdom of Great Britain and Northern Ireland',
              'New Zealand': 'New Zealand', 'Other': 'Other'})]),
    'ky9u6': ('end', [demo('age', AGE, None),
                      demo('gender', GENDER, {o: o for o in (
                          'Woman', 'Man', 'Non-binary or gender fluid')})]),
    'kxcwm': ('end', [
        demo('age', AGE, None),
        demo('gender', GENDER, {'Female': 'female', 'Male': 'male',
                                'Other / non-binary': 'other / non-binary',
                                'Prefer not to say': 'prefer not to say'}),
        demo('employment', 'What is your current employment status?',
             {o[0].upper() + o[1:]: o for o in (
                 'working full-time', 'working part-time', 'unemployed or looking for work',
                 'homemaker or stay-at-home parent', 'student', 'retired',
                 'prefer not to say')}),
        demo('education', 'What is the highest level of education you have completed?',
             {o[0].upper() + o[1:]: o for o in (
                 'some high school or less', 'high school diploma or GED',
                 'some college, but no degree', "associate's or technical degree",
                 "Bachelor's degree", 'graduate or professional degree',
                 'prefer not to say')}),
        demo('household_income', 'What is your annual household income?',
             {o[0].upper() + o[1:]: o for o in (
                 'less than $25,000', '$25,000 - $49,000', '$50,000 - $74,000',
                 '$75,000 - $99,999', '$100,000 - $149,000', '$150,000 or more',
                 'prefer not to say')})]),
}


def with_demographics(name, built):
    if name not in DEMOGRAPHICS:
        return built
    where, qs = DEMOGRAPHICS[name]
    page = {'type': 'page', 'items': copy.deepcopy(qs)}

    def add(blocks):
        return [page] + blocks if where == 'start' else blocks + [page]
    out = dict(built)
    if 'arm_blocks' in out:
        out['arm_blocks'] = [add(b) for b in out['arm_blocks']]
    else:
        out['blocks'] = add(out['blocks'])
    return out


LISTINGS = {
    'kfrux': kfrux, 'cse5r': cse5r, 'efk28': efk28, 'fkrsd': fkrsd, '6fjdr': sixfjdr,
    '6cxdn': sixcxdn, '9ebhq_S1': ninebhq_s1, '9ebhq_S2': ninebhq_s2,
    'hvdwk_S2': hvdwk_s2, 'hvdwk_S3': hvdwk_s3, 'aj5mt': aj5mt, 'ba65f_A': ba65f_a,
    'ba65f_B': ba65f_b, 'dqsv6': dqsv6, 'ky9u6': ky9u6, 'kf4e6': kf4e6, 'fxp7g': fxp7g,
    'kxcwm': kxcwm,
}

#: Targets moved by the revised findings: the deployed one was demoted to secondary
#: (cse5r f04, kxcwm f65, 6cxdn f35, ky9u6 f20) or changed meaning (ba65f f16). The replacement is the main,
#: scored finding in the SAME archive study, so no listing changes experiment.
TARGETS = {'cse5r': 'f24', 'kxcwm': 'f85', 'ba65f_A': 'f09', 'ba65f_B': 'f09',
           '6cxdn': 'f39', 'ky9u6': 'f31'}


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
        new.update(with_demographics(name, build(old)))
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
