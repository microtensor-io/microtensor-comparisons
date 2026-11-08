# ctx_compress exp2: the epoch 0 winner with a repair step

Run date: 2026-11-08. Arena: `ctx_compress` on Bittensor testnet, epoch 0.

**Status: complete.** Same 36 sessions, reader, judge, grader and settings as [exp1](../exp1/README.md).

## Question

exp1 found that the epoch 0 winner (UID 2, weights `e7528c49…`) fails most items on format: it loops to the 3,072 token cap and loses its later headings. How does it score when a repair step makes sure all nine headings are there before grading?

## Contestants

| ID | Contestant |
|---|---|
| M1 | UID 2 model, weights `e7528c49…`, rerun on a rented RTX 4090. All 36 summaries came out byte for byte identical to exp1's M1. |
| R1 | M1's summaries passed through the repair step |

## The repair step

The arena's harness rules allow one full pass and one repair pass, with at most 3 s added per item. This repair is code with no second model call (`comparisons/repair.py`):

1. A summary that already has the nine headings in order and fits its budget is left alone.
2. Otherwise it drops repeated runs of 2 to 40 words and repeated lines, which is what the model's loops are.
3. It puts the remaining text under the nine headings in the arena's order. A heading the model never wrote reads `Not recorded.`.
4. If the result is still over the item's budget, it trims the longest section from the end. No item needed this.

On these 36 summaries it changed 30, added 153 missing headings, dropped 532 repeated lines and 12,507 repeated words, and took 19 ms per summary (median, at most 54 ms).

## Settings

Everything is as in exp1: the arena's prompt, temperature 0, at most 3,072 output tokens, seed 0, `vllm/vllm-openai@sha256:6ee13335…` with prefix caching off and one sequence at a time, the grader from subnet commit `09b3ed7c` (`compress.py` is unchanged since), the same probe model and server, Qwen 3.8 27B as reader and Gemma 4 31B as judge on the same llama.cpp build, and the same random seed. Weights came from the server's public mirror and were checked against `e7528c49…` before the run.

The M1 reader replies and judge votes are exp1's, because its summaries are identical. R1 was read and judged fresh. Regrading M1 gave the same grade as exp1 on all 36 items.

## Results

| | M1, without repair | R1, with repair |
|---|---|---|
| Passed, of 36 | 5 | **12** |
| Pass rate (Wilson 95%) | 13.9% (6.1% to 28.7%) | 33.3% (20.2% to 49.7%) |
| Kept all 9 headings | 6 | 36 |
| Within budget | 31 | 36 |
| Recall of key facts | 47.5% | 47.5% |
| Hallucination | 2.9% | 2.9% |
| Continuation (scorable summaries only) | 0.73 on 6 | 0.50 on 36 |
| Planted facts recalled by the reader, of 306 | 56 (18.3%) | 57 (18.6%) |
| Confident wrong answers, of 360 | 3.3% | 2.8% |
| Commitments kept, of 27 | 15 | 16 |
| Median time per compaction | 32.1 s | 32.1 s |
| p95 time | 34.2 s | 34.2 s |
| Median time to first token | 3.6 s | 3.6 s |
| GPU cost per compaction | $0.0067 | $0.0067 |
| Cost per compaction with the list price ($0.01 per 1M input tokens, output free) | $0.0073 | $0.0073 |

Paired exact McNemar tests on the arena pass, against exp1:

| Pair | Only the first passed | Only the second passed | p |
|---|---|---|---|
| R1 against M1 | 7 | 0 | 0.016 |
| R1 against Qwen 3.8 27B (exp1 F1) | 2 | 8 | 0.11 |
| R1 against Gemma 4 31B (exp1 F2) | 4 | 4 | 1.0 |

## Reading it

- **The repair step more than doubles the pass rate,** from 5 to 12 of 36 (p = 0.016), and every summary now keeps its headings and budget.
- **It does not add facts.** Recall, hallucination and the reader's planted fact recall are the same within one fact, because the repair only removes repeats and adds headings.
- **12 of 36 is level with Gemma 4 31B in exp1** (also 12, p = 1.0) and below Qwen 3.8 27B (18, p = 0.11), at about a fifth of their cost per compaction and a sixth of their time.
- **What still fails is the loop itself.** 8 of the 24 failures have a recall of 0: the model looped before it wrote anything useful, and the repair can only fill empty headings. The other 16 have content but score under 0.60. Stopping the loop in the model, or in a repair pass that calls the model, is what would move these.
- **The rerun is exact.** The same weights, image and settings on another rented RTX 4090 gave the same 36 summaries. The rerun took 32.1 s per compaction against 28.5 s in exp1, so the card itself was about 12% slower.

## Limits of this run

- Everything in exp1's limits applies.
- The repair is code, with no second model call. A repair pass that asks the model to rewrite its own output is allowed by the arena's rules and was not tried.
- `Not recorded.` headings pass the format gate but carry no content, so a repaired summary can pass while being thin under some headings.
- Time and cost come from this rerun's card, which was slower than exp1's. The repair adds milliseconds.
- The judge agreement is low, kappa 0.40 on 15 replies, so read the commitments row as rough.

## Files

| File | Contents |
|---|---|
| `results/work/outputs/M1.jsonl` | The rerun summaries with tokens and times |
| `results/work/outputs/R1.jsonl` | The repaired summaries, each with a `repair` record of what changed |
| `results/work/graded/<ID>.jsonl` | Every grade with the probe model's answers |
| `results/work/reader.jobs.results.jsonl` | Reader replies: R1 from this run, M1 from exp1 |
| `results/work/judge.jobs.results.jsonl`, `judge.key.json` | Judge votes and the blind key; M1's entries are exp1's, prefixed `e1` |
| `results/work/pod_info.json`, `open_pod_info.json`, `grader_info.json`, `pod_log.txt` | Card, image, price, grader and the 4090 pod's log |
| `results/raw.jsonl` | One row per contestant and item with the summary and every metric |
| `results/summary.csv`, `results/analysis.json` | The table above, the repair counts and the rerun check |
| `results/comparison.json` | The document on the Models page: exp1's document with R1 added as a contestant, its paired tests and a note |

## Rerun

Follow [docs/reproduce.md](../../docs/reproduce.md) steps 1 to 4 for M1 with `--work ctx_compress/exp2/results/work`, then:

```bash
python -m comparisons.repair --work ctx_compress/exp2/results/work --source M1 --out R1 --cache .cache
python -m comparisons.grade M1 R1
python -m comparisons.jobs reader --package sources/compaction-study-replication \
  --work ctx_compress/exp2/results/work --contestants R1
python -m comparisons.jobs judge --package sources/compaction-study-replication \
  --work ctx_compress/exp2/results/work --contestants R1
python -m comparisons.exp2 --package sources/compaction-study-replication
```

Run grading with `RUN_WORK=ctx_compress/exp2/results/work` as in step 4, and the reader and judge jobs as in step 5.
