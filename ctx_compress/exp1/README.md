# ctx_compress exp1: compaction models against frontier

Run date: 2026-11-06. Arena: `ctx_compress` on Bittensor testnet, epoch 0.

**Status: partial.** The four local models are summarised, graded and analysed. The four frontier contestants, the reader and the judge have not been run, so the planted fact and commitment numbers do not exist yet for anyone.

## Question

On a dataset we did not make, how do the top three models of the first `ctx_compress` epoch compare with frontier models and with the base model they were fine tuned from, on pass rate, recall, hallucination, cost and time?

## Dataset

Source: Woolford's replication package, https://github.com/felixwoolford/compaction-study-replication at commit `8c7c35f5d3222909c1ac8ef4bc44f90ba6a61512`, MIT licence.

| Set | Contents | Cut point | Items |
|---|---|---|---|
| A, planted facts | 18 synthetic debugging sessions made by the package's own generator (scenario `s1.json`, seed 5101). Each has 17 planted facts and 3 lures: 306 facts and 54 lures. | The study's first compaction point: the plant phase and round 1. | 18 |
| B, commitments | 18 real public Pi coding agent sessions from MIT licensed sources, verified by SHA-256. 29 commitment probes, of which the study scores 27. | The end of the session. The probe message comes after it. | 18 |

What happened when the cuts became arena items:

- **Nothing was dropped.** The rendered sessions are 38,914 to 109,268 tokens (median 66,490). The limit is 122,880.
- **Rendering is the arena's.** Each session is converted with the `pi` parser in the public arenas package and rendered inside `<session>` tags exactly as in the arena. That rendering keeps the head and tail of long tool output and does not carry the agent's thinking blocks.
- **33 planted facts are out of reach.** They were planted only in thinking blocks, so no contestant can see them. The most any contestant can recall is 273 of 306. All 99 tool output facts, all 99 user facts, all 42 assistant text facts and all 33 superseded facts are in the rendered text.
- **Every commitment survives.** The key strings of all 29 commitment probes appear in the rendered sessions.
- **Arena labels.** Key facts and continuation probes come from the arena's own builder. 8 facts and 1 probe that pointed at text the rendering trims were removed, so that every label can be answered from the session. There is no "next step" probe, because both cut points are followed by a new user message that nobody could predict.
- **Check.** `mta check` reports 36 items and 0 problems.

Files: `data/items.jsonl` (one row per item; the study's probes are under `label.attached`), `data/report.json` (the counts above), SHA-256 of `items.jsonl`: `c61e850fe00c50237a7be1e21e43f1c1acfa545e66ac66f693a56e41036a877a`.

## Contestants

| ID | Contestant | Runs on | Status |
|---|---|---|---|
| M1 | UID 2 model, weights `e7528c49…` | RTX 4090 | Done |
| M2 | UID 13 model, weights `b0bd36e4…` | RTX 4090 | Done |
| M3 | UID 14 model, weights `84b5d274…` | RTX 4090 | Done |
| B0 | Granite 4.0 H Micro base, revision `d5f01a3e…` | RTX 4090 | Done |
| F1 | Claude Haiku 5.5 | API | Not run |
| F2 | GLM 5.3 Flash | API | Not run |
| F3 | Claude Sonnet 5.5 | API | Not run |
| P1 | Claude Sonnet 5.5 with Pi's own compaction prompt (the study's baseline) | API | Not run |
| C1 | Ceiling: the reader sees the full cut | Reader only | Not run |
| C0 | Floor: the reader sees the last 3,072 tokens of the cut | Reader only | Not run |

M1, M2 and M3 are archived at `microtensor-io/ctx_compress-e7528c49`, `microtensor-io/ctx_compress-b0bd36e4` and `microtensor-io/ctx_compress-84b5d274` on Hugging Face. The repos are public and gated: request access once.

## Settings

| Setting | Value |
|---|---|
| Prompt | The arena's compaction instruction as the system message and the rendered session as the user message. P1 uses Pi 1.1.0's prompt instead (`results/work/pi_prompt.json`). |
| Decoding | Temperature 0, at most 3,072 output tokens, stop at `<|end_of_text|>`, seed 0 |
| Engine | `vllm/vllm-openai@sha256:6ee133356d49ed24cee03dd0cda3d3980279a11c107ce3e752c89e76540f41c9`, context 125,952 tokens, one sequence at a time, bfloat16, prefix caching off |
| Card | One NVIDIA GeForce RTX 4090, 24 GB |
| Pass mark | Item score of at least 0.60 |
| Grader | `microtensor_subnet/validator/compress.py` from the public subnet repo, commit `09b3ed7c9f98825c6a35cfd5183bad961bc06d6d` |
| Probe model | `Qwen/Qwen2.5-1.5B-Instruct-GGUF`, file `qwen2.5-1.5b-instruct-q8_0.gguf`, revision `91cad51170dc346986eccefdc2dd33a9da36ead9`, at most 64 output tokens |
| Probe server | `ghcr.io/ggml-org/llama.cpp@sha256:43b3988c22c00faae3d04a8f6e3eba41403dff7c5f5952490599f1bcbdc6f3c2`, CPU, 4 threads |
| Tokenizer | `ibm-granite/granite-4.0-h-micro@d5f01a3ea75f088947be3aae039f4ad52837dfde` |
| Reader (not run) | Claude Sonnet 5.5, temperature 0, one probe per call |
| Judge (not run) | Claude Opus 5.5, three votes per reply, blind to the contestant; Claude Sonnet 5.5 rescores a random 25% |
| Random seed for sampling | 20261106 (judge order, second judge sample, hand check sample) |

## Results so far

36 items per contestant. Full table: `results/summary.csv`. One row per contestant and item, with the summary text and every metric: `results/raw.jsonl`.

| | M1 (UID 2) | M2 (UID 13) | M3 (UID 14) | B0 (base) |
|---|---|---|---|---|
| Passed | 5 | 5 | 3 | 0 |
| Pass rate | 13.9% | 13.9% | 8.3% | 0% |
| Wilson 95% interval | 6.1% to 28.7% | 6.1% to 28.7% | 2.9% to 21.8% | 0% to 9.6% |
| Kept all 9 headings | 6 | 7 | 20 | 12 |
| Within budget | 31 | 30 | 34 | 33 |
| Recall of key facts | 47.5% | 46.3% | 32.6% | 27.2% |
| Hallucination | 2.9% | 1.8% | 3.0% | 7.3% |
| Continuation (scorable summaries only) | 0.73 on 6 | 0.66 on 7 | 0.54 on 20 | 0.38 on 12 |
| Median time | 28.5 s | 28.6 s | 13.6 s | 11.6 s |
| p95 time | 30.5 s | 30.7 s | 30.1 s | 28.4 s |
| Median time to first token | 3.4 s | 3.4 s | 3.4 s | 3.5 s |
| GPU cost per compaction | $0.0059 | $0.0064 | $0.0044 | $0.0034 |
| Cost per compaction with the $0.005 selling price | $0.0109 | $0.0114 | $0.0094 | not sold |
| Mean output tokens | 2,474 | 2,680 | 1,719 | 1,263 |

Where the items went, out of 36:

| | Passed | Right format, score under 0.60 | Failed a format gate |
|---|---|---|---|
| M1 (UID 2) | 5 | 1 | 30 |
| M2 (UID 13) | 5 | 2 | 29 |
| M3 (UID 14) | 3 | 17 | 16 |
| B0 (base) | 0 | 12 | 24 |

Reading it:

- **Format is the main failure for the two best models.** M1 reached the 3,072 token limit on 25 items and M2 on 28, usually by repeating one phrase. A summary cut off that way is missing its later headings and scores zero.
- **When they finish, they are good.** M1's complete summaries average an item score of 0.72 and 5 of 6 pass.
- **M3 finishes more often and scores lower.** 20 complete summaries, average item score 0.47, 3 passes.
- **Fine tuning moved the right things.** Against the base model the best fine tuned model recalls 75% more key facts and invents 75% fewer identifiers. It is slower and costs more GPU time, because it writes longer outputs.

## Limits of this run

- **36 items is a small sample.** The Wilson intervals are wide. M1 and M2's true pass rate could sit anywhere from 6% to 29%.
- **No frontier numbers yet.** Nothing here says how these models compare with Haiku, GLM or Sonnet.
- **No reader or judge yet.** Planted fact recall, confident wrong answers and commitment pass rates are not measured for any contestant, and the paired McNemar tests in `results/tests.csv` are empty.
- **Continuation is measured only on scorable summaries.** A summary that fails format or budget scores zero whatever its continuation would be, so the probe model was not run on those.
- **The pod price was the secure cloud price.** No cheaper community card was free at the time, so GPU cost uses $0.89 an hour.
- **Set A was generated with Python 3.11.** The replication package asks for 3.14. The generator only uses the standard library's seeded random module, and the built plans passed the package's own consistency checks.
- **The hand check is not done.** `results/hand_check.md` lists ten summaries drawn at random for a person to read against their sessions.
- **Epoch 0 arena scores are not comparable to these.** The arena used 25 hidden items of its own kind per pool. This run uses 36 sessions of a different shape.

## Files

| File | Contents |
|---|---|
| `data/items.jsonl` | The 36 items |
| `data/report.json` | Token range, drops, planted fact and commitment counts |
| `results/work/outputs/<ID>.jsonl` | Every raw summary with tokens, time to first token and total time |
| `results/work/graded/<ID>.jsonl` | Every grade with the probe model's answers |
| `results/work/pod_info.json` | Card, image and price of the GPU run |
| `results/work/grader_info.json` | Probe model, image, command and grading rules |
| `results/work/pi_prompt.json` | Pi's compaction prompt, taken from its published package |
| `results/raw.jsonl` | One row per contestant and item with the summary and all metrics |
| `results/summary.csv` | One row per contestant |
| `results/tests.csv` | McNemar tests (empty until frontier runs) |
| `results/comparison.json` | The document the Models page reads |
| `results/hand_check.md` | The ten summaries for the hand check |

`results/chart.png` is not included yet. It will be drawn when the frontier contestants have run, since a chart of four nearby points says little.

## Rerun

See [docs/reproduce.md](../../docs/reproduce.md).
