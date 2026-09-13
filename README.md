# Validating Reconstructed Experiments

Participant-facing experiments for Stanford IRB protocol **88942** (Non-Medical,
Expedited, umbrella). Eighteen Prolific listings reproducing fifteen archived studies.

Generated — do not edit by hand. The source of truth is
`mega_archive_replicate/replication/`; rebuild with

```
python3 replication/battery_build.py      # regenerate specs from the archive
python3 replication/battery_deploy.py     # regenerate this repo
```

## Layout

```
lib/render.js  lib/app.css     the renderer, shared by every listing
<listing>/index.html           one directory per Prolific listing
<listing>/spec.json            items, stimuli, scales, conditions
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
unattributable data. Condition assignment is derived deterministically from the
Prolific ID and is re-checked at ingest.

## The eighteen listings

| # | listing | study | N | minutes |
|---|---|---|---|---|
| 01 | `kfrux` | Judging a designer's approach | 120 | 1 |
| 02 | `kf4e6` | Reading a short passage | 150 | 1 |
| 03 | `efk28` | Judging a life story | 230 | 1 |
| 04 | `cse5r` | Forming a workplace committee | 360 | 1 |
| 05 | `6fjdr` | The impact of everyday climate actions | 430 | 1 |
| 06 | `fkrsd` | Habits and holidays | 80 | 1 |
| 07 | `6cxdn` | Your romantic relationship | 130 | 4 |
| 08 | `ba65f_A` | Short scenarios about two friends | 27 | 20 |
| 09 | `ba65f_B` | Short scenarios about two friends | 53 | 7 |
| 10 | `aj5mt` | Reasoning about likelihoods | 230 | 6 |
| 11 | `dqsv6` | Views about Britain and world affairs | 170 | 6 |
| 12 | `9ebhq_S1` | Beliefs about widely discussed claims | 110 | 4 |
| 13 | `9ebhq_S2` | Beliefs about widely discussed claims | 150 | 4 |
| 14 | `fxp7g` | Reading news headlines | 80 | 9 |
| 15 | `ky9u6` | Personality and well-being | 80 | 9 |
| 16 | `hvdwk_S2` | Views on environmental sustainability | 40 | 7 |
| 17 | `hvdwk_S3` | Views on environmental sustainability | 40 | 11 |
| 18 | `kxcwm` | Creativity exercises and ways of thinking | 80 | 17 |

## Note on visibility

This repository is public, so every instrument is readable. `spec.json` also carries
all arms of a randomised listing, so a participant could in principle read the other
conditions. Both were accepted deliberately for these minimal-risk studies; if that
changes, split the specs per arm in `battery_build.py` and serve from a private repo.
