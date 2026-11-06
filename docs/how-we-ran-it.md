# How we ran ctx_compress exp1

This is the record of our own run on 2026-11-06 (UTC): which machines, which images, what it cost and what went wrong. The commands in [reproduce.md](reproduce.md) do the same work with open tools.

## Machines

| Role | Machine | Used for |
|---|---|---|
| Workstation | Windows PC, Python 3.11 | Building the items, analysis |
| Control machine | Cloud VM, 4 vCPU, 16 GB | Driving the GPU pod, running the probe server and the grader |
| GPU | One rented NVIDIA GeForce RTX 4090, 24 GB, secure cloud, 0.89 USD an hour | Running M1, M2, M3 and B0 |
| GPU | Up to twelve rented NVIDIA A40, 48 GB, secure cloud, 0.59 USD an hour each | Running Qwen 3.8 27B and Gemma 4 31B as summarisers, reader and judge |

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

## Larger open models, reader and judge

The first plan used closed API models. The provider account was out of credit, so the run used the two open weight models the study itself ran.

- Server: `ghcr.io/ggml-org/llama.cpp@sha256:821d0ae4…` (CUDA build `b12124`) on rented NVIDIA A40 cards, 48 GB, secure cloud, 0.59 USD an hour. The server downloads the model file itself: `unsloth/Qwen3.8-27B-GGUF:UD-Q6_K_XL` or `unsloth/gemma-4-31B-it-GGUF:UD-Q5_K_XL`.
- Flags: context 131,072 tokens, one slot, all layers on the GPU, flash attention on, thinking off. `tools/open_pod.py` holds the exact command.
- Up to twelve pods ran at once so the work finished in about two and a half hours: two for Qwen's summaries, three for Gemma's, two for Qwen with Pi's prompt, two for the reader on the full sessions, two with four slots each for the reader on summaries, and the Gemma pods again for the judge.
- One Gemma session is 131,921 tokens in Gemma's tokenizer, so it ran on a pod started with a context of 139,264 tokens.
- `comparisons/run.py jobs --stream` drove every call from our workstation. It streams, asks the server for prompt progress so the connection never goes quiet, and retries when a stream drops.
- Reader: Qwen 3.8 27B, 3,483 calls. Judge: Gemma 4 31B, 243 verdicts, one vote each. Second judge: Qwen 3.8 27B on 61 replies. Agreement between the two: kappa 0.51.
- Grading of the three new contestants ran on the control machine with the same probe server as before, about one minute per scorable summary.

Timeline on Nov 6:

| Step | Time (UTC) |
|---|---|
| First pod started | 10:04 |
| Gemma summaries done | 11:29 |
| Qwen summaries done, both prompts | 11:53 |
| Reader done | 12:15 |
| Judge done, last pod deleted | 12:25 |

## Cost

| Item | Cost |
|---|---|
| RTX 4090, about 65 minutes at 0.89 USD an hour | about 0.97 USD |
| A40 pods for the open models, reader and judge, about 20 pod hours at 0.59 USD an hour | about 11.90 USD |

Cost per compaction in the results is the card's hourly price times the time of that call. For the three Microtensor models the tables also show that figure plus the list price, which is 0.01 USD per million input tokens with output tokens free.

## Things that went wrong

- **First GPU attempt stopped before the first call.** Our driver read the prompt from the wrong field of the arena definition. It was fixed and restarted; the pod from the failed attempt was deleted by the driver.
- **No community priced card was available.** Both GPU runs used the secure cloud price.
- **Streams to the open model pods dropped.** Connections from our workstation broke mid stream on roughly one call in four. The runner first waited minutes before retrying, then was changed to retry after 45 quiet seconds. A retry resumes from the server's prompt cache, so its measured time leaves out the prompt. 21 Qwen summaries ended that way. Timing reruns for them were started and then stopped because they kept dropping too, so their time is the measured generation time plus prompt time fitted on the clean rows of the same model. Every Gemma time is measured.
- **Two runners doubled up on one pod for a few minutes.** A stopped runner had not actually exited. The affected Gemma results were thrown away and rerun before anything was graded.
- **The judge sometimes wrapped its verdict.** Gemma often put the verdict object under a key copied from the brief's examples. The parser accepts both forms.
- **Grading was moved.** The first plan was to grade on the machine that runs our validator. We ran the probe server and grader on the control machine instead, as a standalone server from the same pinned image.
- **One continuation average was corrected.** An early figure for M1 (0.67) included one incomplete summary that had been probed before the "scorable only" rule was applied. The published figure (0.73 on 6 summaries) counts only complete summaries, the same rule as for every other contestant.

## Where the numbers on the site come from

`results/comparison.json` is posted to the Microtensor server as the `comparison` document of `ctx_compress` epoch 0. The Models page reads it through `GET https://api.microtensor.cloud/v2/comparisons`. When more contestants finish, the document is rebuilt and posted again, and the page updates on its own.
