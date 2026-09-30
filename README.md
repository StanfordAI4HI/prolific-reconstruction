# Validating Reconstructed Experiments

Participant-facing experiments for Stanford IRB protocol **88942** (Non-Medical,
Expedited, umbrella). Eighteen Prolific listings reproducing fifteen archived studies.

Generated — do not edit by hand. The source of truth is
`mega_archive_replicate/replication/`; rebuild with

```
python3 replication/battery_build.py      # regenerate specs from the archive
python3 replication/battery_deploy.py     # regenerate this repo
python3 tools/respec_battery.py           # then re-derive the fifteen listings below
```

`battery_build.py` cuts the reconstructions down in ways that change what participants
see (dropped items before the outcome, lost or invented randomisation, flattened
branching, mislabelled targets). `tools/respec_battery.py --full` re-derives all
eighteen listings from the reconstructions alone (`final/experiment_N.json`, never the
raw deposit), so the re-run tests the reconstruction and not the converter. Its
docstring states the rules; run it after every `battery_build.py`, or that build's
errors come back. It reads `prolific_battery_v1/studies/` beside this repository when
no `--archive` is given. It also closes every listing with the site's own items (an
instructed-response attention check and the demographics the findings read, named
`participant-info.<field>`), regenerates the consent description, time and pay from
the built instrument, and writes `PROLIFIC_SETTINGS.md` and the table below.
Reconstruction item text and scales are never changed; an error there is what the
re-run measures. `node tools/test_render.js` drives the renderer over every spec and
checks each conversion fix (needs `npm install --no-save jsdom`).

## Layout

```
lib/render.js  lib/app.css     the renderer, shared by every listing
<listing>/index.html           one directory per Prolific listing
<listing>/spec.json            items, stimuli, scales, conditions
tools/respec_battery.py        re-derives the listings from the reconstructions
tools/test_render.js           headless run of every spec through the renderer
PROLIFIC_SETTINGS.md           per-listing Prolific settings (generated)
```

## Data

Responses are submitted to [proliferate](https://proliferate.alps.science), operated
by the Stanford ALPS Lab, which stores them and redirects the participant to the
Prolific completion URL configured on the proliferate side. Nothing is written to
GitHub, and this repository holds no participant data.

Create one proliferate experiment per listing, with `experiment_URL` set to the
Pages URL below and `completion_URL` set to the Prolific completion URL for that
listing.

## Prolific study URL

```
https://stanfordai4hi.github.io/prolific-reconstruction/<listing>/?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

The renderer refuses to run without a `PROLIFIC_PID`, so a bare link cannot produce
unattributable data. Condition assignment is derived deterministically from
proliferate's `participant_id` (or `PROLIFIC_PID` when run without proliferate) and is
re-checked at ingest by hashing the same id.

## The eighteen listings

| # | listing | study | N | minutes |
|---|---|---|---|---|
| 01 | `kfrux` | Judging a designer's approach | 120 | 2 |
| 02 | `kf4e6` | Reading a short passage | 150 | 1 |
| 03 | `efk28` | Judging a life story | 230 | 5 |
| 04 | `cse5r` | Forming a workplace committee | 360 | 11 |
| 05 | `6fjdr` | The impact of everyday climate actions | 430 | 10 |
| 06 | `fkrsd` | Habits and holidays | 80 | 12 |
| 07 | `6cxdn` | Your romantic relationship | 130 | 17 |
| 08 | `ba65f_A` | Short scenarios about two friends | 27 | 20 |
| 09 | `ba65f_B` | Short scenarios about two friends | 53 | 7 |
| 10 | `aj5mt` | Reasoning about likelihoods | 230 | 8 |
| 11 | `dqsv6` | Views about Britain and world affairs | 170 | 6 |
| 12 | `9ebhq_S1` | Beliefs about widely discussed claims | 110 | 7 |
| 13 | `9ebhq_S2` | Beliefs about widely discussed claims | 150 | 11 |
| 14 | `fxp7g` | Reading news headlines | 80 | 12 |
| 15 | `ky9u6` | Personality and well-being | 80 | 39 |
| 16 | `hvdwk_S2` | Views on environmental sustainability | 40 | 16 |
| 17 | `hvdwk_S3` | Views on environmental sustainability | 40 | 13 |
| 18 | `kxcwm` | Creativity exercises and ways of thinking | 80 | 22 |

## Note on visibility

This repository is public, so every instrument is readable. `spec.json` also carries
all arms of a randomised listing, so a participant could in principle read the other
conditions. Both were accepted deliberately for these minimal-risk studies; if that
changes, split the specs per arm in `battery_build.py` and serve from a private repo.
