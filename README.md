# Microtensor comparisons

Each Microtensor arena certifies small specialist models. This repository holds the experiments that test those models against frontier models and against the base model they were fine tuned from, on a dataset somebody else published. Everything needed to check or rerun an experiment is here: the items, the code, every model output, every grade and the exact versions used.

The live summary of each run is on the Models page of the site, under **Compare with frontier**: https://www.microtensor.cloud/products/registry?tab=compare

## Runs

| Arena | Run | Dataset | Status | Report |
|---|---|---|---|---|
| `ctx_compress` (agent session compaction) | exp1, 2026-11-06 | Woolford compaction study replication package | Local models done. Frontier models, reader and judge not run yet. | [ctx_compress/exp1](ctx_compress/exp1/README.md) |

## What the first run found

Four models summarised 36 coding agent sessions on one RTX 4090. A summary passes when our arena grader scores it at least 0.60 and it keeps every format rule.

| Model | Passed | Pass rate | 95% lower bound | Kept all 9 headings | Recall | Hallucination | Median time |
|---|---|---|---|---|---|---|---|
| UID 2 (fine tuned) | 5 of 36 | 13.9% | 6.1% | 6 of 36 | 47% | 2.9% | 28.5 s |
| UID 13 (fine tuned) | 5 of 36 | 13.9% | 6.1% | 7 of 36 | 46% | 1.8% | 28.6 s |
| UID 14 (fine tuned) | 3 of 36 | 8.3% | 2.9% | 20 of 36 | 33% | 3.0% | 13.6 s |
| Granite 4.0 H Micro (base) | 0 of 36 | 0% | 0% | 12 of 36 | 27% | 7.3% | 11.6 s |

In plain terms:

- The fine tuned models do not carry their arena results over to this dataset. UID 2 passed 25 of 25 hidden arena items and passes 5 of 36 here.
- The failure is mostly format. On these sessions the two strongest models often repeat one phrase until they reach the 3,072 token limit and never write the later headings. 30 and 29 of their 36 summaries fail for that reason alone. When UID 2 does finish, 5 of its 6 complete summaries pass.
- Fine tuning still helped. Against the base model, recall rose from 27% to 47% and invented identifiers fell from 7.3% to 1.8%.
- The comparison with frontier models is not in yet. Those contestants are defined and their jobs are built, but they have not been run.

## How an experiment works

1. **Dataset.** Take published sessions and their probes. Cut each session once, at the point the source study compacted it.
2. **Items.** Convert each cut to the arena's session format, render it the way the arena does, and build the arena's own labels from it.
3. **Summarise.** Every contestant gets the same instruction and the same rendered session, at temperature 0, with the same output limit.
4. **Grade.** The arena's grader scores every summary: format, budget, key fact recall, invented identifiers and continuation probes.
5. **Probe.** A fixed reader model answers the source study's own questions from each summary alone. Rules score the planted facts and a blind judge scores the commitments.
6. **Report.** Rates with Wilson intervals, paired McNemar tests, time and cost.

## Layout

| Path | What it holds |
|---|---|
| `ctx_compress/exp1/README.md` | The run report: dataset, contestants, settings, results, limits |
| `ctx_compress/exp1/data/` | The 36 items in the arena format, with the attached probes |
| `ctx_compress/exp1/results/` | Every summary, every grade, the tables, and the document the site reads |
| `comparisons/` | The code: build items, run models, grade, build reader and judge jobs, analyse |
| `tools/` | Two small scripts that fetch and generate the source sessions |
| `docs/reproduce.md` | Step by step instructions to rerun everything |
| `docs/how-we-ran-it.md` | The machines, images, commands and costs of our own run |
| `docs/metrics.md` | Every metric and how it is computed |
| `NOTICE.md` | Third party material and its licences |

## Rerun it

Start with [docs/reproduce.md](docs/reproduce.md). Rebuilding the items and regrading our saved summaries needs only a CPU and Docker. Rerunning the local models needs one GPU with 24 GB of memory and access to the archived models, which are public but gated on Hugging Face.

## Licence

The code and results are under the terms in [LICENSE](LICENSE). The dataset comes from MIT licensed sources that keep their own licence; see [NOTICE.md](NOTICE.md).
