# ctx_compress on CPU: what fits a 4 core, 20 minute evaluation

Run date: 2026-11-17. Arena: `ctx_compress`.

**Status: complete.** No model was trained for this run. Every number is for public models, sessions generated from public code, or the public sessions of [exp1](../exp1/README.md).

## Question

Can a small compaction model be scored on CPU with fresh sessions every evaluation, inside a sandbox of 4 CPU cores and 4 GiB of memory, with a hard ceiling of 20 minutes per evaluation and a typical run of 10? And is the score steady enough that a new entry which beats the top score by 1% is really better?

## Short answer

- **Speed fits.** A 1B model summarises a 2,000 to 4,000 token session in 23 to 33 seconds on 4 cores. With session generation and grading in the same evaluation, 15 to 21 sessions fit in 10 minutes and 31 to 43 in 20, depending on the CPU.
- **Memory fits.** Nothing measured went above 2.1 GiB for a short session.
- **A 1% lead does not hold.** Scored on 16 fresh sessions, the same model's score moves by about 15% of itself from one set of sessions to the next (one standard deviation). That is 15 times the 1% lead. An unchanged model scored again on new sessions beats its own earlier score by 1% about half the time.
- **Training does not close the gap.** A model that kept the format on every session would still move by about 4% at 16 sessions. It would need about 300 sessions for the noise to match a 1% lead, and about 4,750 for it to fall to a quarter of the lead.
- **Real long sessions do not fit.** Compressed in chunks, one real session of 39,000 to 109,000 tokens takes 6 to 24 minutes on 4 cores.

## Setup

| Part | What we used |
|---|---|
| Model | `ibm-granite/granite-4.0-h-1b-GGUF` at `c2cb1972f511add21f3bae244990b8ff3a3ffb23`, `granite-4.0-h-1b-Q4_K_M.gguf`, as published (not fine tuned). For speed only: `ibm-granite/granite-4.0-h-350m-GGUF` at `a864f823cce6e6048b5752e2816fe7a23987d790`, `granite-4.0-h-350m-Q8_0.gguf`. |
| Engine | llama.cpp build b11977, CPU image `ghcr.io/ggml-org/llama.cpp@sha256:846ee6837e29060357252abcc084b1c51e7f8f8f9081acebfd5ba50a461566b9`. 4 threads, context 8,192 tokens, one request at a time, prompt cache off. Temperature 0, seed 0. |
| Machines | Cloud CPU instances with 4 vCPUs each, of two types: AMD EPYC 9575F and AMD EPYC 4564P. One model per instance, nothing else running. |
| Sessions | The arena's public session generator, `microtensor-io/microtensor-arenas` at `2ab703a447ba8a23aecc31c094427dc0399cbb10` (`arenas/compress/synth.py`): a small Python project with a bug report, and a coding agent's tool calls and real tool outputs up to a cut point, rendered the arena's way. All sessions were made from 14 seeds (101 to 114), 12 sessions per seed. |
| Session shape | 2,000 to 4,000 tokens (2,010 to 3,889, mean 2,776). Every session has exactly 3 key facts and 6 questions: 2 from the arena's own probes on where the work stood, 3 that ask which of four names appeared in the session, and 1 that asks which of four tasks the agent was working on. The wrong options are names and tasks from other sessions of the same seed that do not occur in this one. |
| Summary | The arena's compaction instruction, nine fixed headings, at most 500 tokens. |
| Grading | The arena grader, `microtensor-io/microtensor-subnet` at `9fb9621bf82563d62e21b67dd6a0a4aa78c6fa2d`. The reader is `Qwen/Qwen2.5-1.5B-Instruct-GGUF` at `91cad51170dc346986eccefdc2dd33a9da36ead9`, `qwen2.5-1.5b-instruct-q8_0.gguf`, on llama.cpp b11977 on 4 CPU threads. The budget is counted with the `ibm-granite/granite-4.0-h-micro` tokenizer at `d5f01a3ea75f088947be3aae039f4ad52837dfde`. A session passes at an item score of 0.60. |

## Timing and memory

Each figure is per session, for the 1B, on 168 sessions (60 on the EPYC 9575F, 108 on the EPYC 4564P).

| Step | EPYC 9575F | EPYC 4564P |
|---|---|---|
| Read the session (2,776 tokens on average) | 12.0 s | 17.5 s |
| Write the summary (433 tokens on average) | 11.0 s | 14.9 s |
| Summary, mean | 23.0 s | 32.5 s |
| Summary, 90th percentile | 27.2 s | 40.1 s |
| Summary, slowest | 39.5 s | 45.4 s |
| Grade one summary with the reader | 5.0 s | 5.7 s |
| Generate one session | 3.9 s | 4.2 s |
| **Sessions that fit in 10 minutes** | **21** | **15** |
| **Sessions that fit in 20 minutes** | **43** | **31** |

How the fit is counted: 30 seconds to start (checking and converting the model file takes 5 seconds, then loading and one warm up request), then for each session its generation and its summary. Grading runs on the scorer's own cores while the next summary is written, and takes less time than a summary, so it adds nothing. The slowest summary we saw, 45.4 seconds, would still let 16 sessions finish in about 14 minutes.

| Process | Peak memory |
|---|---|
| Check the model file and convert it to a llama.cpp file | 2.06 GiB, for 5 s |
| 1B engine, sessions of 2,000 to 4,000 tokens | 1.87 GiB |
| 350M engine, the same sessions | 0.56 GiB |
| Reader server, prompt cache capped at 256 MiB | 2.05 GiB |
| 1B engine, sessions of 8,000 to 16,000 tokens | 2.22 GiB |
| 1B engine, sessions of 39,000 to 66,000 tokens | 3.27 GiB |

We also ran the whole loop in two containers, model and scorer, each limited to 4 CPUs and 4 GiB, with six sessions of 8,000 to 10,000 tokens. Neither container ran out of memory. The model's container peaked at 2.06 GiB by Docker's count.

### Why the sessions are short

Reading slows down as the session grows. The 1B on the EPYC 4564P:

| Session tokens | Read | Summary tokens | Write | Total |
|---|---|---|---|---|
| 2,776 (mean of 108) | 17.5 s | 433 | 14.9 s | 32.5 s |
| 8,326 | 59.9 s | 329 | 13.4 s | 73.3 s |
| 16,516 | 174.0 s | 306 | 23.3 s | 197.4 s |
| 38,927 | 361.6 s | 1,200 | 142.9 s | 504.6 s |
| 66,503 | 787.5 s | 93 | 18.3 s | 806.1 s |

A session of 8,000 tokens already takes over a minute, so about 7 would fit in 10 minutes. A session of 66,000 tokens takes over 13 minutes on its own.

## Scores

All 168 sessions, untuned 1B:

| | 1B as published |
|---|---|
| Mean item score | 0.550 |
| Passed (0.60 or more) | 100 of 168 (59.5%) |
| Kept all nine headings | 128 of 168 |
| Within 500 tokens | 168 of 168 |
| Recall of key facts | 77.2% |
| Invented identifiers | 2.6% |
| Mean summary length | 433 tokens |

The 350M against the 1B on the same 24 sessions (seeds 111 and 112, EPYC 9575F):

| | 1B | 350M |
|---|---|---|
| Mean item score | 0.613 | 0.176 |
| Passed | 15 of 24 | 5 of 24 |
| Kept all nine headings | 20 of 24 | 6 of 24 |
| Recall of key facts | 76.4% | 76.4% |
| Invented identifiers | 2.1% | 1.7% |
| Mean summary length | 432 tokens | 261 tokens |
| Summary time, mean | 22.4 s | 7.8 s |
| Peak memory | 1.86 GiB | 0.56 GiB |

The 350M finds the facts as well as the 1B and is about three times faster. It loses on format: 18 of its 24 summaries miss a heading and score 0.

## Round to round noise

Each seed stands for one evaluation round with fresh sessions.

- **The rounds differ only by which sessions they draw.** The 14 round means at 12 sessions run from 0.379 to 0.702, with a standard deviation of 0.100. Drawing 12 sessions at random from all 168 predicts 0.094. Nothing else moves between rounds.
- **One session scores far from the next.** The standard deviation of a single session's score is 0.326, against a mean of 0.550. The main cause is the format gate: 40 of the 168 summaries missed a heading and scored 0, and every one of the 40 zeros has that cause. The 128 summaries that kept the format average 0.72, with a standard deviation of 0.12.

Noise at each number of sessions, as one standard deviation of the evaluation score from one set of fresh sessions to the next:

| Sessions per evaluation | 1B as published: noise | Noise ÷ 1% lead | Unchanged model beats its own earlier score by 1% | Model that always keeps the format: noise | Noise ÷ 1% lead | Unchanged model beats its own earlier score by 1% |
|---|---|---|---|---|---|---|
| 16 | 14.8% | 15 | 48% | 4.3% | 4.3 | 44% |
| 43 | 9.0% | 9.0 | 47% | 2.7% | 2.7 | 39% |
| 100 | 5.9% | 5.9 | 45% | 1.7% | 1.7 | 35% |
| 400 | 3.0% | 3.0 | 40% | 0.87% | 0.87 | 21% |

The model that always keeps the format is projected from the 128 summaries that did, as if every summary had.

Sessions needed per evaluation:

| Target | 1B as published | Model that always keeps the format |
|---|---|---|
| Noise equal to the 1% lead | 3,515 | 297 |
| Noise a quarter of the 1% lead | 56,237 | 4,752 |

Two ways to lower the noise did not help:

- **Scoring each question instead of each session.** At 16 sessions the noise is 15.6% scored per question and 14.9% scored per session.
- **The same number of facts and questions in every session.** Every session here already has exactly 3 facts and 6 questions; the noise above is what is left.

## What a trained 350M would add

Measured: the 350M reads 2.4 times as fast as the 1B and writes 2.3 times as fast per token. Estimated, for a 350M trained to keep the format and write summaries as long as the 1B's:

| | EPYC 9575F | EPYC 4564P |
|---|---|---|
| Summary time | about 9.6 s | about 13.5 s |
| Sessions in 10 minutes | about 42 | about 32 |
| Sessions in 20 minutes | about 86 | about 66 |
| Noise at the 10 minute count | about 2.6% | about 3.0% |

Session generation (about 4 seconds a session) then becomes a quarter to a third of each session's time. Twice the sessions cut the noise by only 1.4 times: it stays at 2 to 3 times the 1% lead, against the quarter that is needed. Whether a 350M can be trained to keep the format and its recall is not measured here.

## Real long sessions compressed in chunks

The 18 real public coding agent sessions of exp1 (set B, 38,914 to 109,268 tokens). The untuned 1B summarised each one in two ways:

- **In chunks.** The rendered session is cut on line boundaries into pieces of about 3,000 tokens. Each call gets the summary so far and the next piece, and writes an updated summary of at most 1,000 tokens. The last summary is the answer. Sessions took 15 to 40 calls (27 on average).
- **In one call.** The whole session in one request, with a context of 116,000 tokens.

These two runs used a GPU to save time, with the same model file and engine build, and the same grader and reader as exp1. The other rows are exp1's stored grades for the same 18 sessions.

| Model | Mean item score | Passed | Kept all nine headings | Recall of key facts |
|---|---|---|---|---|
| 1B in chunks | 0.143 | 0 of 18 | 12 of 18 | 18.3% |
| 1B in one call | 0.000 | 0 of 18 | 0 of 18 | 19.7% |
| UID 2 (fine tuned 3B, epoch 0 winner) | 0.036 | 1 of 18 | 1 of 18 | 35.6% |
| UID 14 (fine tuned 3B) | 0.300 | 2 of 18 | 11 of 18 | 37.1% |
| Granite 4.0 H Micro (base 3B) | 0.098 | 0 of 18 | 4 of 18 | 37.0% |
| Qwen 3.8 27B | 0.526 | 8 of 18 | 18 of 18 | 77.2% |
| Gemma 4 31B | 0.520 | 6 of 18 | 18 of 18 | 57.0% |

In plain terms:

- Chunking lets the 1B keep the format, which it never does in one long call. That alone puts it above the epoch 0 winner, which loops on inputs this long.
- It recalls about half the key facts the 3B models do, passes no session, and is far behind the 27B and 31B models.

Time on CPU: in chunks the 1B reads 86,573 tokens and writes 14,597 per session on average. At the speeds measured on the short sessions:

| | EPYC 9575F | EPYC 4564P |
|---|---|---|
| One real session in chunks, mean | 12.4 min | 17.5 min |
| Shortest to longest | 5.6 to 16.8 min | 7.9 to 23.5 min |

One real session fills most of a 20 minute evaluation, and the longest does not fit.

## What this means

On 4 cores in 20 minutes, a small model can be run and graded on fresh short sessions, but its score cannot separate two models that differ by 1%. The noise from drawing new sessions is 15 times the lead at the 16 sessions that fit in about 10 minutes, and about 4 times the lead even for a model that never misses the format. A lead decided by 1% would mostly follow which sessions a round happened to draw.
