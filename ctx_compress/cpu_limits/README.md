# ctx_compress on CPU: what fits a 4 core, 20 minute evaluation

Run date: 2026-11-17. Arena: `ctx_compress`.

**Status: complete.** No model was trained for this run. Every number is for public models, sessions generated from public code, or the public sessions of [exp1](../exp1/README.md).

## Question

Can a small compaction model be scored on CPU inside a sandbox of 4 CPU cores and 4 GiB of memory, with a hard ceiling of 20 minutes per evaluation and a typical run of 10? Does the same file get the same score every time? And is the score steady enough that a new entry which beats the current leader by 1% is really better?

## Short answer

- **Speed fits.** A 1B model summarises a 2,000 to 4,000 token session in 22 to 35 seconds on 4 cores. 15 to 21 sessions fit in a typical 10 minute evaluation, depending on the CPU.
- **Memory fits.** Nothing measured on a short session went above 2.1 GiB.
- **The same file gets the same score, but only on CPUs that run the same llama.cpp kernel, and only with time to spare.** Two CPU models that use the same kernel gave byte identical summaries and the same score on every run. A third CPU model, which llama.cpp gives a different kernel, changed every summary. Shipping only one kernel makes them agree. A session that runs close to the time limit makes the score depend on how busy the machine is.
- **A 1% lead does not hold, even when leader and challenger are scored on the same sessions.** Any change to the model's weights, down to 0.01% noise on the normalisation weights or another quantisation of the same weights, rewrites every summary. Fifteen versions of one model scored between 0.42 and 0.65 on the same 16 sessions. Any one of them beats another by more than 1% about half the time.
- **More sessions or a fixed set do not close the gap.** At 36 sessions the versions still spread by about 9%, and a fixed set makes the best of many copies look about 20 to 35% better than the model really is.
- **Real long sessions do not fit.** Compressed in chunks, one real session of 39,000 to 109,000 tokens takes 6 to 24 minutes on 4 cores.

## Setup

| Part | What we used |
|---|---|
| Model | `ibm-granite/granite-4.0-h-1b-GGUF` at `c2cb1972f511add21f3bae244990b8ff3a3ffb23`, `granite-4.0-h-1b-Q4_K_M.gguf`, as published (not fine tuned). For speed only: `ibm-granite/granite-4.0-h-350m-GGUF` at `a864f823cce6e6048b5752e2816fe7a23987d790`, `granite-4.0-h-350m-Q8_0.gguf`. |
| Engine | llama.cpp build b11977, CPU image `ghcr.io/ggml-org/llama.cpp@sha256:846ee6837e29060357252abcc084b1c51e7f8f8f9081acebfd5ba50a461566b9`. 4 threads, context 8,192 tokens, one request at a time, prompt cache off. Temperature 0, seed 0. |
| Machines | Cloud CPU instances with 4 vCPUs each, of three types: AMD EPYC 9575F, AMD EPYC 4564P and AMD EPYC 7713. One model per instance. |
| Sessions | The arena's public session generator, `microtensor-io/microtensor-arenas` at `2ab703a447ba8a23aecc31c094427dc0399cbb10` (`arenas/compress/synth.py`): a small Python project with a bug report, and a coding agent's tool calls and real tool outputs up to a cut point, rendered the arena's way. |
| Session shape | 2,000 to 4,000 tokens. Every session has exactly 3 key facts and 6 questions: 2 from the arena's own probes on where the work stood, 3 that ask which of four names appeared in the session, and 1 that asks which of four tasks the agent was working on. The wrong options are names and tasks from other sessions of the same set that do not occur in this one. |
| Summary | The arena's compaction instruction, nine fixed headings, at most 500 tokens. |
| Grading | The arena grader, `microtensor-io/microtensor-subnet` at `9fb9621bf82563d62e21b67dd6a0a4aa78c6fa2d`. The reader is `Qwen/Qwen2.5-1.5B-Instruct-GGUF` at `91cad51170dc346986eccefdc2dd33a9da36ead9`, `qwen2.5-1.5b-instruct-q8_0.gguf`, on llama.cpp b11977 on 4 CPU threads. The budget is counted with the `ibm-granite/granite-4.0-h-micro` tokenizer at `d5f01a3ea75f088947be3aae039f4ad52837dfde`. A session passes at an item score of 0.60. |

Two experiments used these parts:

- **Fresh sessions.** 168 sessions from 14 seeds (101 to 114), 12 per seed, each seed standing for one evaluation round.
- **Same sessions.** One secret seed made 36 sessions (set B, whose first 16 are the fixed set A) and 16 more held back (set C). The untuned 1B and 16 copies of it were scored on these sets with the entry check, conversion and engine control of a scorer we built, and the arena grader with a fresh reader server for every evaluation.

## Timing and memory

Each figure is per session, for the 1B, on the 168 fresh sessions (60 on the EPYC 9575F, 108 on the EPYC 4564P).

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

How the fit is counted: 30 seconds to start (checking and converting the model file takes 5 seconds, then loading and one warm up request), then for each session its generation and its summary. Grading runs on the scorer's own cores while the next summary is written, and takes less time than a summary, so it adds nothing.

On the 1,096 summaries of the same session experiment the spread was wider: 22.3 s on average on the EPYC 9575F (slowest 36.1 s) and 34.6 s on the EPYC 4564P (90th percentile 45.4 s, slowest 59.1 s). Instances of the same 4564P type differed: one averaged 27.8 s per session, another 43.0 s. A 36 session evaluation, grading included, took 15.9 to 17.1 minutes on the 9575F and 20.3 to 29.8 minutes on the 4564P.

| Process | Peak memory |
|---|---|
| Check the model file and convert it to a llama.cpp file | 2.06 GiB, for 5 s |
| 1B engine, sessions of 2,000 to 4,000 tokens | 1.87 GiB |
| 350M engine, the same sessions | 0.56 GiB |
| Reader server, prompt cache capped at 256 MiB | 2.05 GiB |
| 1B engine, sessions of 8,000 to 16,000 tokens | 2.22 GiB |
| 1B engine, sessions of 39,000 to 66,000 tokens | 3.27 GiB |

We also ran the whole loop in two containers, model and scorer, each limited to 4 CPUs and 4 GiB, with six sessions of 8,000 to 10,000 tokens. Neither container ran out of memory. The model's container peaked at 2.06 GiB by Docker's count.

Packing a model file into the entry format took about 7 times the file's size in memory (6.6 GiB for the 0.9 GB Q4_K_M file), so the 1.2 GB Q6_K and 1.6 GB Q8_0 files could not be packed on an 8 GiB machine. Converting a packed entry back took 2.06 GiB for the 0.9 GB file; larger entries were not measured.

### Why the sessions are short

Reading slows down as the session grows. The 1B on the EPYC 4564P:

| Session tokens | Read | Summary tokens | Write | Total |
|---|---|---|---|---|
| 2,776 (mean of 108) | 17.5 s | 433 | 14.9 s | 32.5 s |
| 8,326 | 59.9 s | 329 | 13.4 s | 73.3 s |
| 16,516 | 174.0 s | 306 | 23.3 s | 197.4 s |
| 38,927 | 361.6 s | 1,200 | 142.9 s | 504.6 s |
| 66,503 | 787.5 s | 93 | 18.3 s | 806.1 s |

A session of 8,000 tokens already takes over a minute, so about 7 would fit in 10 minutes. A session of 66,000 tokens takes over 13 minutes on its own. The generator could not make 36 sessions of 1,000 to 2,000 tokens with 2 or 3 key facts each: a cut that early comes before the agent has touched enough files.

## Scores

All 168 fresh sessions, untuned 1B:

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

## Same file, same score

The untuned 1B was scored again and again on the same sessions, each time with a fresh conversion, engine and reader:

| Where | Runs | Result |
|---|---|---|
| EPYC 9575F and EPYC 4564P, 10 instances | 10 runs of set A, 2 of set B, 2 of set C, and repeats on the same instance | Byte identical summaries, identical grades and identical scores every time: 0.4532 on A, 0.5811 on B, 0.4531 on C |
| EPYC 7713, 2 instances, 65 s per session | 4 runs of set A | Every summary differs from the 9575F and 4564P ones. Sessions took about 60 s and 8 or 9 of 16 ran past the time limit. Scores 0.300, 0.347, 0.347 and 0.347 |
| EPYC 9575F with only the AVX2 kernel, 2 instances | 2 runs of set A | Identical to each other (0.4458) and identical to the EPYC 7713 summaries on every session the 7713 finished: 8 of 8 at a 65 s limit, 11 of 11 at a 240 s limit |

What this shows:

- **The kernel decides the text.** llama.cpp's CPU image carries several kernels and picks one per CPU. The 9575F and 4564P get the same one; the 7713, which has no AVX-512, gets another, and every summary changes. Shipping only the AVX2 kernel makes every one of these CPUs run the same arithmetic. It costs speed: 31.9 s per session on the 9575F against 22.3 s.
- **The clock decides the rest.** On two EPYC 7713 instances one session took 48.9 s on one and ran past the 63.5 s limit on the other, so the same file scored 0.300 once and 0.347 three times. A later run on one of them took 121 s per session, twice as long as before, and 5 sessions ran past even a 240 s limit. Wherever a session comes near the limit, the score depends on how busy the machine is.
- **Generation is stable.** The same seed gave byte identical sessions on all 15 instances and all three CPU models.

## Copies of one model on the same sessions

A takeover rule can compare a new entry with the current leader on the same sessions, by scoring the leader again alongside each challenger. Round to round noise (next section) then cancels. What is left is how far two entries of equal quality land apart on the same sessions.

We made 16 copies of the untuned 1B that are no better than it:

- 3 other quantisations of the same weights from IBM's repository: Q4_K_S, Q5_K_S and Q5_K_M;
- 13 copies with the normalisation weights multiplied by (1 + d × random noise): 3 with d = 1%, 8 with d = 0.1%, 2 with d = 0.01%.

Every copy passed the entry check and changed every summary it wrote: 36 of 36 on set B and 16 of 16 on set C, including the two copies with 0.01% noise. Within the 52 sessions none scored measurably better or worse than the base model (paired test, every |t| below 1.6).

The base model and 14 copies (the two 0.01% copies kept apart) on the same sessions:

| Sessions | Lowest | Highest | Spread around the mean | One beats another by more than 1% |
|---|---|---|---|---|
| Set A, 16 sessions | 0.422 | 0.651 | 15.0% | 48.6% of pairs |
| Set B, 36 sessions | 0.471 | 0.622 | 9.4% | 47.1% of pairs |
| Set C, 16 fresh sessions | 0.329 | 0.693 | 18.7% | 49.5% of pairs |

The last column counts, for every ordered pair of the 15 versions, whether one scores more than 1% above the other. With a spread this much wider than 1%, it can only come out near half, so it measures how wide the spread is compared with the lead rather than anything about quality.

Why the spread is so wide:

- **Format flips.** In 22% of sessions a copy kept all nine headings where the base model did not, or the other way round, which moves that session between 0 and a full score. Nearly every one of these zeros is a summary cut off at the 500 token limit before its ninth heading: 217 of the 227 failures stop at the limit, at 492 tokens on average. The flips account for about 84% of the difference between two versions.
- **Answers.** One different answer to one question in a session that passes moves a 16 session score by up to 0.0052, more than 1% of a score of 0.45. At 36 sessions one answer moves it by up to 0.0023.
- **Without the flips it is still too wide.** On the sessions where both versions keep the headings, two versions differ by 9.1% at 16 sessions and 5.7% at 36, and one beats the other by more than 1% 46% and 39% of the time.

For an equal copy to clear a 1% lead in at most 1 try in 20, an evaluation would need about 19,500 sessions like these; about 3,200 if no version ever lost a heading; about 1,200 if only the recall of key facts were scored. That is about what the fresh session noise below asks for, because a copy rewrites every summary much as a new set of sessions does.

Other changes we checked against the same data do not get there: more questions per session (even with every answer difference removed, a copy still wins 48% of the time at 36 sessions), averaging several decodes of each session (the spread falls with the square root of the number of decodes, no faster than more sessions), scoring only sessions the reference model passes (47 to 48%), and dividing by a reference model's score (both sides share the factor). Copies with a smaller change do not spread less: 6.1% for 0.01% noise, 7.6% for 0.1%, 9.0% for 1% and 11.2% for another quantisation, all at 36 sessions against the base model.

### A fixed set of sessions

If the same 16 sessions were used for many evaluations, copies would be lottery tickets drawn against one fixed set:

- **The winner on the fixed set is not better.** The copy that scored best on set A, 22% above the average copy, was 3% above the average copy on the held back set C. Across the 14 copies, the score on A and the score on C are not correlated (−0.13 at 16 sessions, −0.27 at 36; with 14 copies, a moderate correlation cannot be ruled out).
- **Keeping the best inflates the score.** Keeping the best of 8 copies puts the fixed set score about 18% above what the model averages on those sessions; the best of 120 about 32%, and of 600 about 37%. On 36 sessions: 12%, 21% and 25%. These come from drawing each session's score from the 15 measured versions; the real copies spread a little more than the simulated ones, so they are if anything low.
- **The lead still changes hands at once.** Against a typical leader, at least one of 4 to 8 equal copies beats it by more than 1% in 75 to 80% of rounds. Against a leader that happened to score high on the fixed set, none wins: 3 of the 15 versions were beaten by none of the other 14 on set A, so a genuinely better model would also struggle to pass it.

## Fresh sessions: round to round noise

Each seed of the fresh session experiment stands for one evaluation round. This noise matters when a new score is compared with a score earned on other sessions; when the leader is scored again on the challenger's sessions, it cancels and the copy spread above is what counts.

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

Session generation (about 4 seconds a session) then becomes a quarter to a third of each session's time. Twice the sessions cut the noise by only 1.4 times: it stays at 2 to 3 times the 1% lead, against the quarter that is needed. Whether a 350M can be trained to keep the format and its recall is not measured here, nor how far its copies would spread.

## Real long sessions compressed in chunks

The 18 real public coding agent sessions of exp1 (set B, 38,914 to 109,268 tokens). The untuned 1B summarised each one in two ways:

- **In chunks.** The rendered session is cut on line boundaries into pieces of about 3,000 tokens. Each call gets the summary so far and the next piece, and writes an updated summary of at most 1,000 tokens. The last summary is the answer. Sessions took 15 to 40 calls (27 on average).
- **In one call.** The whole session in one request, with a context of 116,000 tokens.

These two runs used a GPU to save time, with the same model file and engine build, and the same grader and reader as exp1. The other rows are exp1's stored grades for the same 18 sessions.

| Model | Mean item score | Passed | Kept all nine headings | Recall of key facts |
|---|---|---|---|---|
| 1B in chunks | 0.143 | 0 of 18 | 12 of 18 | 18.3% |
| 1B in one call | 0.000 | 0 of 18 | 0 of 18 | 19.7% |
| UID 14 (fine tuned 3B) | 0.300 | 2 of 18 | 11 of 18 | 37.1% |
| Granite 4.0 H Micro (base 3B) | 0.098 | 0 of 18 | 4 of 18 | 37.0% |
| Qwen 3.8 27B | 0.526 | 8 of 18 | 18 of 18 | 77.2% |
| Gemma 4 31B | 0.520 | 6 of 18 | 18 of 18 | 57.0% |

In plain terms:

- Chunking lets the 1B keep the format, which it never does in one long call.
- It recalls about half the key facts the 3B models do, passes no session, and is far behind the 27B and 31B models.

Time on CPU: in chunks the 1B reads 86,573 tokens and writes 14,597 per session on average. At the speeds measured on the short sessions:

| | EPYC 9575F | EPYC 4564P |
|---|---|---|
| One real session in chunks, mean | 12.4 min | 17.5 min |
| Shortest to longest | 5.6 to 16.8 min | 7.9 to 23.5 min |

One real session fills most of a 20 minute evaluation, and the longest does not fit.

## What this means

On 4 cores in 20 minutes, a small model can be run and graded on short sessions, and the same file gets the same score as long as every evaluation runs the same llama.cpp kernel with time to spare. But the score cannot separate two models that differ by 1%. A copy that is no better than the leader, made by changing its weights by 0.01%, rewrites every summary and lands 10 to 19% away from the leader on the same sessions: as often above the 1% bar as below it. More sessions within the time limit and a fixed set of sessions both leave that in place, and a fixed set adds a winner that is only lucky on that set.
