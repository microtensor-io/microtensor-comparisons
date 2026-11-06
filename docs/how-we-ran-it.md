# How we ran ctx_compress exp1

This is the record of our own run on 2026-11-06 (UTC): which machines, which images, what it cost and what went wrong. The commands in [reproduce.md](reproduce.md) do the same work with open tools.

## Machines

| Role | Machine | Used for |
|---|---|---|
| Workstation | Windows PC, Python 3.11 | Building the items, analysis |
| Control machine | Cloud VM, 4 vCPU, 16 GB | Driving the GPU pod, running the probe server and the grader |
| GPU | One rented NVIDIA GeForce RTX 4090, 24 GB, secure cloud, 0.89 USD an hour | Running M1, M2, M3 and B0 |

## Local models

- The GPU pod's own image was the arena's pinned engine, `vllm/vllm-openai@sha256:6ee13335…`. A small worker on the pod downloaded each model, started the engine with the arena's settings and timed each call next to the engine.
- M1, M2 and M3 were loaded at the exact revisions scored in epoch 0. Their files were checked against the SHA-256 hashes in the network's mirror before the engine started. B0 was loaded from `ibm-granite/granite-4.0-h-micro` at the arena's reference revision.
- One model at a time. After each model the engine was stopped and its files were deleted before the next download.
- For each model: one short warm up call, then the 36 items one after another, never in parallel.
- Engine settings: context 125,952 tokens, memory share 0.9, one sequence at a time, bfloat16, prefix caching off, seed 0.

Timeline:

| Step | Time (UTC) |
|---|---|
| Pod started | 23:55 on Nov 5 |
| M1 done | 00:15 |
| M2 done | about 00:33 |
| M3 and B0 done, pod deleted | 01:01 |

The pod was up for about 65 minutes and cost about 0.97 USD.

Our internal driver for this step talks to our pod worker and is not in this repository. `comparisons/run.py engine` sends the same request to any engine started with the same image and flags. We have not yet rerun the 36 items through `run.py` ourselves, so treat a first rerun as the test of that script.

## Grading

- Probe server: `ghcr.io/ggml-org/llama.cpp@sha256:43b3988c…` on the control machine, CPU only, 4 threads, with `Qwen/Qwen2.5-1.5B-Instruct-GGUF` (`qwen2.5-1.5b-instruct-q8_0.gguf`, revision `91cad511…`).
- Grader: the arena's `compress.py`, run from an image that carries the public subnet code. The probe prompt and request are the validator's own.
- The validator runs this probe with 8 threads. We used 4 because the control machine has 4 cores. Thread count changes speed, not answers.
- The probe model was asked only about summaries that had all nine headings and fit the budget: 6, 7, 20 and 12 summaries for M1, M2, M3 and B0. The others score zero whatever the probe would say.
- Grading the four models took about 50 minutes.

## Frontier models, reader and judge

Not run. The jobs for the four frontier summarisers were built (144 calls). Small test calls to all four models succeeded, but every call above a few thousand tokens was refused by the provider, which points to the account being out of credit. Nothing from those attempts is in the results.

## Cost

| Item | Cost |
|---|---|
| RTX 4090, about 65 minutes at 0.89 USD an hour | about 0.97 USD |
| Frontier calls | 0 USD (not run; estimate about 95 USD) |

Cost per compaction in the results is the card's hourly price times the measured time of that call. For the three Microtensor models the tables also show that figure plus the list price, which is 0.01 USD per million input tokens with output tokens free.

## Things that went wrong

- **First GPU attempt stopped before the first call.** Our driver read the prompt from the wrong field of the arena definition. It was fixed and restarted; the pod from the failed attempt was deleted by the driver.
- **No community priced card was available.** The run used the secure cloud price.
- **Grading was moved.** The first plan was to grade on the machine that runs our validator. We ran the probe server and grader on the control machine instead, as a standalone server from the same pinned image.
- **One continuation average was corrected.** An early figure for M1 (0.67) included one incomplete summary that had been probed before the "scorable only" rule was applied. The published figure (0.73 on 6 summaries) counts only complete summaries, the same rule as for every other contestant.

## Where the numbers on the site come from

`results/comparison.json` is posted to the Microtensor server as the `comparison` document of `ctx_compress` epoch 0. The Models page reads it through `GET https://api.microtensor.cloud/v2/comparisons`. When more contestants finish, the document is rebuilt and posted again, and the page updates on its own.
