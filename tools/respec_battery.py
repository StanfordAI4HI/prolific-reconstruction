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


STUDIES = _archive() / 'runs/replication/prolific_battery_v1/studies'

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

    def people(self, **meta):
        return [p for p in self.ex['data']
                if all(p['participant-meta'].get(k) == v for k, v in meta.items())]

    def sequence(self, longest=False, **meta):
        """The modal presentation order of the matching participants, as their items.

        `longest` takes the fullest path instead, for studies whose orders differ
        only because answers hid items."""
        people = self.people(**meta)
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


def upto(items, last):
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
        if it.get('variable-name', '').startswith('drop_habit_'):
            by_label[text.split('? ', 1)[1]] = it['variable-name']
    # "follow-up return/keep questions were shown only for likelihood ratings > 50"
    for it in out:
        if it.get('variable-name', '').startswith('return_home_'):
            gate = by_label[it['question'].split('? ', 1)[1]]
            it['show_if'] = {'variable': gate, 'op': '>', 'value': 50}
    return {'blocks': out}


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


def fxp7g(spec):
    r = Recon('fxp7g', 'experiment_4')
    conds = ['control', 'manipulated_goal', 'measured_goal', 'measured_site_preference']
    labels, arms = [], []
    for c in conds:
        for s in (1, 2):
            items = r.sequence(condition=c, set=s)
            first = next(i for i, it in enumerate(items)
                         if it['variable-name'].startswith('likelihood_sentiment_h'))
            runs = collections.OrderedDict()
            for it in items[first:]:
                runs.setdefault(it['variable-name'].rsplit('_h', 1)[1], []).append(it)
            labels.append({'condition': c, 'set': str(s)})
            # "headline order randomized"
            arms.append(items[:first] + [shuffle([seq(*v) for v in runs.values()])])
    return {'arms': len(arms), 'arm_keys': ['condition', 'set'], 'arm_labels': labels,
            'arm_blocks': arms}


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


LISTINGS = {
    'efk28': efk28, 'fkrsd': fkrsd, '6fjdr': sixfjdr, '6cxdn': sixcxdn,
    '9ebhq_S1': ninebhq_s1, '9ebhq_S2': ninebhq_s2, 'hvdwk_S2': hvdwk_s2,
    'hvdwk_S3': hvdwk_s3, 'aj5mt': aj5mt, 'ba65f_A': ba65f_a, 'dqsv6': dqsv6,
    'ky9u6': ky9u6, 'kf4e6': kf4e6, 'fxp7g': fxp7g, 'kxcwm': kxcwm,
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


def main():
    check = '--check' in sys.argv
    for name, build in LISTINGS.items():
        old = _load(name)
        new = copy.deepcopy(old)
        for k in ('blocks', 'arms', 'arm_keys', 'arm_labels', 'arm_blocks'):
            new.pop(k, None)
        new.update(build(old))
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
