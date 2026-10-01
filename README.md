# Validating Reconstructed Experiments

Participant-facing experiments for Stanford IRB protocol **88942** (Non-Medical,
Expedited, umbrella). Eighteen Prolific listings reproducing fifteen archived studies.

Generated — do not edit by hand; `battery_deploy.py` rewrites this file. Rebuild with

```
python3 replication/battery_build.py      # regenerate specs from the archive
python3 tools/respec_battery.py --full    # re-derive the listings (see below)
#   then copy the rebuilt spec.json files back into replication/apps/
python3 replication/battery_deploy.py     # regenerate this repo
```

`battery_build.py` cuts the reconstructions down in ways that change what participants
see (dropped items before the outcome, lost or invented randomisation, flattened
branching, mislabelled targets). `tools/respec_battery.py` re-derives the listings from
the reconstructions alone (`final/experiment_N.json`, never the raw deposit), so the
re-run tests the reconstruction and not the converter. Its docstring states the rules;
run it after every `battery_build.py`, or that build's errors come back. `--full`
fields each instrument end to end rather than stopping at the outcome item.

`ba65f_B` is left as built on purpose: its `balanced` block forces each participant
through five high-cost and five low-cost scenarios out of the ten, and regenerating it
generically would replace that with independent draws.

`respec_battery.py` is therefore the source of truth for what each listing asks, and
`lib/render.js` here is the source of truth for the renderer — `replication/apps/`
holds copies of both. `battery_deploy.py` refuses to publish a listing with fewer
questions than the deployed one, or a renderer older than the deployed one, so a stale
copy cannot silently undo this. `node tools/test_render.js` drives the renderer over
every spec (needs `npm install --no-save jsdom`).

## Layout

```
lib/render.js  lib/app.css     the renderer, shared by every listing
<listing>/index.html           one directory per Prolific listing
<listing>/spec.json            items, stimuli, scales, conditions
tools/respec_battery.py        re-derives the listings from the reconstructions
tools/test_render.js           headless run of every spec through the renderer
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

| # | listing | study | N | minutes | arms | debug link |
|---|---|---|---|---|---|---|
| 01 | `kfrux` | Judging a designer's approach | 120 | 1 | 3 | [debug](https://proliferate.alps.science/experiment/32f9c699-e124-4b30-a394-ecd21889f09b/debug) |
| 02 | `kf4e6` | Reading a short passage | 150 | 1 | 4 | [debug](https://proliferate.alps.science/experiment/df15f48c-ac4e-4975-94b8-b273abf3c4f3/debug) |
| 03 | `efk28` | Judging a life story | 230 | 5 | 6 | [debug](https://proliferate.alps.science/experiment/6bfd017c-0642-4ad4-a4c7-578f638ab401/debug) |
| 04 | `cse5r` | Forming a workplace committee | 360 | 10 | 2 | [debug](https://proliferate.alps.science/experiment/7a3e7758-b245-43e8-9b1f-e7b57b3e8736/debug) |
| 05 | `6fjdr` | The impact of everyday climate actions | 440 | 10 | 1 | [debug](https://proliferate.alps.science/experiment/2ab3c7c1-b6f1-45d6-87b6-a5ecf1024ce8/debug) |
| 06 | `fkrsd` | Habits and holidays | 80 | 12 | 1 | [debug](https://proliferate.alps.science/experiment/85cd14df-1564-4491-ac1c-2a797047f167/debug) |
| 07 | `6cxdn` | Your romantic relationship | 80 | 16 | 1 | [debug](https://proliferate.alps.science/experiment/88cd8ab4-972d-4765-a24b-f7d802b4dbbb/debug) |
| 08 | `ba65f_A` | Short scenarios about two friends | 30 | 20 | 1 | [debug](https://proliferate.alps.science/experiment/e2653cfb-a802-42f5-9ffd-c74c624c42a0/debug) |
| 09 | `ba65f_B` | Short scenarios about two friends | 50 | 7 | 1 | [debug](https://proliferate.alps.science/experiment/ba6be750-44c9-4ace-b46c-d3245fd57b71/debug) |
| 10 | `aj5mt` | Reasoning about likelihoods | 230 | 7 | 6 | [debug](https://proliferate.alps.science/experiment/c637ac22-b60d-4855-a9fa-1311b6735075/debug) |
| 11 | `dqsv6` | Views about Britain and world affairs | 180 | 6 | 1 | [debug](https://proliferate.alps.science/experiment/b261283e-0f76-47b2-b331-e20057743cc3/debug) |
| 12 | `9ebhq_S1` | Beliefs about widely discussed claims | 180 | 6 | 1 | [debug](https://proliferate.alps.science/experiment/9f35a038-98ed-47d0-89e8-a9b2372e9c63/debug) |
| 13 | `9ebhq_S2` | Beliefs about widely discussed claims | 180 | 10 | 1 | [debug](https://proliferate.alps.science/experiment/a55e36ce-9fe0-4c7f-a191-dc9675a52eb4/debug) |
| 14 | `fxp7g` | Reading news headlines | 300 | 11 | 8 | [debug](https://proliferate.alps.science/experiment/9b8bb2a4-ae78-42a1-b5b4-6e03aae2602a/debug) |
| 15 | `ky9u6` | Personality and well-being | 80 | 38 | 1 | [debug](https://proliferate.alps.science/experiment/a6444ab0-0926-4ed9-a410-29a829e02aba/debug) |
| 16 | `hvdwk_S2` | Views on environmental sustainability | 80 | 14 | 1 | [debug](https://proliferate.alps.science/experiment/acca6f51-9e2e-44f7-9ace-21a4944546f3/debug) |
| 17 | `hvdwk_S3` | Views on environmental sustainability | 80 | 12 | 1 | [debug](https://proliferate.alps.science/experiment/6680057c-11fc-4209-8773-d1f728bffc21/debug) |
| 18 | `kxcwm` | Creativity exercises and ways of thinking | 80 | 21 | 2 | [debug](https://proliferate.alps.science/experiment/7df4e3a1-8424-4109-9d2e-48819893382c/debug) |

A **debug link** opens the listing through proliferate the way a participant reaches
it, but flagged as sandbox. Every visit creates a fresh participant record and draws a
new random arm, so these are how you sweep the conditions of a multi-arm listing by
hand; they are not for leaving open in tabs. A completed run does store sandbox data —
retrieve it with `proliferate getresults --sandbox`, never mixed with live responses.

`kfrux`'s sandbox export schema is locked to an early payload shape (proliferate fixes
the CSV layout on the first submission it ever sees), so its instrument renders
correctly but its sandbox export does not. Use a throwaway listing for round-trip
checks.

## Note on visibility

This repository is public, so every instrument is readable. `spec.json` also carries
all arms of a randomised listing, so a participant could in principle read the other
conditions. Both were accepted deliberately for these minimal-risk studies; if that
changes, split the specs per arm in `battery_build.py` and serve from a private repo.

The debug links above publish each listing's proliferate experiment id. Anyone who
finds them can create sandbox participant records and submit sandbox responses, which
is noise in `getresults --sandbox` rather than contamination of the live collection.
Whether the same id also admits a submission to the LIVE collection has not been
established against proliferate's access model; until it has, treat the ids as
semi-private. If that is not acceptable, drop this column — the same table is
generated into `replication/DEBUG_LINKS.md`, which is not published.
