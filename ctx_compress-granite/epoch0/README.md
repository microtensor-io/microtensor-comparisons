# ctx_compress-granite epoch 0: fail closed, validator spot checks and the two pool payout

Arena: `ctx_compress-granite` on Bittensor testnet, netuid 576, epoch 0 (2026-11-18 to 2026-11-19).

**Status: settled 2026-11-19 13:27 UTC; the chain has paid the settled split since block 8,479,704 (14:31 UTC).** Every figure comes from the public results API (`https://api.microtensor.cloud/v2/...`), the testnet chain (`wss://test.finney.opentensor.ai:443`) and the subnet's own code at the commits named below.

## Short answer

- **Fail closed.** A miner with no spot check result scores 0 in the specialist model pool and the system pool, and its share goes to the miners that were checked. When no coordinator report arrives, the validator keeps the last settled weights and the epoch pays nothing new.
- **Validator spot checks.** A validator ran its own spot check on a rented RTX 4090, the coordinator's card, for one miner of this epoch. It drew the same 40 calls as the coordinator, and all 40 matched, call by call, as the coordinator's did.
- **Two pool payout.** The epoch settled with 60% of miner emission to the specialist model pool and 40% to the system pool, and nothing burned. Both entries were paid from both pools: UID 14 61.54% and UID 1 38.46%, and the chain's incentive matches it. The system pool's reference was measured before settlement: 50 of 50 frontier answers.
- **Separate records.** `ctx_compress` epoch 0 stays archived with its own results, scores and payout ([testnet_576](../../testnet_576/README.md)). This arena has its own epoch 0 record.

## Terms

- **Specialist model:** the small fine tuned model an entry submits.
- **Harness:** code around the model that prepares the prompt and checks or repairs the output.
- **Router:** a small classifier that predicts whether the specialist model's answer will pass.
- **Escalation:** the path that sends an item on to a frontier model.
- **System:** the specialist model, harness, router and escalation working together.
- **Coordinator:** a key with no stake that reruns a sample of each miner's model calls on a GPU and publishes a signed result.
- **Spot check:** that rerun of a sample of a job's calls, compared token for token with the job's recording.
- **Reference:** the frontier model answering each system item directly, which a system's cost and latency are compared with.

## The epoch

| | |
|---|---|
| Arena | `ctx_compress-granite`, agent session compaction, base model `ibm-granite/granite-4.0-h-micro` at `d5f01a3e` |
| Blocks | start 8,473,759, commits open 8,476,144, reveal 8,476,244, close 8,477,343, end 8,479,380; settled 2026-11-19 13:27:52 UTC |
| Items | specialist model pool 50 items and 50 twins; system pool 50 items and 49 twins, each run at the floors 0.80, 0.90, 0.95 and 0.99 |
| Pools | specialist model 60% and system 40% of miner emission; within a pool the top five get 40%, 25%, 15%, 12% and 8%, renormalised over the eligible entries |
| Entries | UID 14 (`5DewpgAD…`) and UID 1 (`5FJC3RQ7…`), both mirrored, both jobs uploaded (497 rows each) |
| Spot checks | 40 of 40 calls matched for each miner |
| Validator | UID 16 (`5Epocha7…`), validator release 0.8.0, mechanism 0.9.0 |

## 1. Fail closed

### What was run

The validator's own epoch code (`microtensor_subnet/validator/epoch.py`), inside the published validator image `ghcr.io/microtensor-io/validator:25ea3bee…` built from subnet commit `25ea3be`, was run against the real signed documents of `ctx_compress` epoch 0, the archived epoch with four graded miners, with the chain replaced by a recorder so the weights it would set could be read. Each case changes one input.

| Case | What changes | Result |
|---|---|---|
| As it happened | nothing | All four miners checked. Weights: UID 2 26.1%, UID 13 16.3%, UID 14 9.8%, UID 1 7.8%, the burned system pool 40% |
| No row for one miner | the coordinator's signed report has no row for UID 2's receipted transcript | UID 2 scores 0 in the specialist model pool and the system pool, with the reason "no spot check result: the coordinator sent no row". Weights: UID 13 30.0%, UID 14 18.75%, UID 1 11.25%, burn 40%. UID 2 gets nothing |
| An unchecked row | the coordinator posts a row for UID 2 marked unchecked, as it does for a miner it did not reach before the deadline | the same as above, with the reason "unchecked: not reached before the report deadline" |
| No coordinator report | the epoch ends with receipted transcripts and no coordinator document | every miner scores 0 with "the coordinator sent no row", and the validator sets the last settled weights instead: exactly the split it had settled before (`held_equals_settled: true`) |
| Reports with no rows | the coordinator posted five signed reports, none with a miner row | the same as no report: the last settled weights |
| Server unreachable | the coordinator document cannot be read | the validator keeps waiting and does not treat the read failure as a missing report |

So a miner with no spot check result is never paid, and a missing coordinator report never moves the weights: the chain keeps paying the last settled split. On the server, an epoch whose uploaded transcripts the coordinator checked none of is settled void, with no ledger payout and no certificates.

## 2. A validator's own spot check

### How it ran

The validator's own spot check code from subnet release 0.8.0 (`microtensor_subnet/validator/rerun`, commit `73d02dd`), the code a validator runs with `MT_SPOT_CHECK_GPUS` set, for UID 14's epoch 0 job. Its GPU was a rented RTX 4090, the P1 card the coordinator uses, running the arena's pinned engine image `vllm/vllm-openai@sha256:6ee13335…`. Everything else came from public inputs.

| Input | Value |
|---|---|
| Transcript | `b2d5ce85…`, matching its receipt leaf |
| Upload block | 8,476,698 |
| Draw block and hash | 8,476,708, `0x349fbf23…` |
| Calls to draw | 40, plus 10 reference answers |
| Weights | the 10 files in the mirror, matching the weights hash the miner was scored under |

### Result

| | Validator | Coordinator |
|---|---|---|
| Calls drawn | 40 | 40 |
| Same 40 calls | yes | |
| Prompts rebuilt | 40 of 40 (31 from the replay of the miner's harness) | |
| Matched | 40 | 40 |
| Mismatched | 0 | 0 |
| Unsettled or errors | 0 | 0 |
| Timed calls | the same calls as the coordinator's | |
| p95 time to first token | 4,308.1 ms | 4,279.7 ms |
| p95 time per output token | 8.23 ms | 8.17 ms |
| Peak memory | 22,988,980,224 bytes | 22,988,980,224 bytes |
| Within the envelope | yes | yes |

Every call's output matched the transcript's recorded output, token for token, at the first run, so no call needed the settle step and no evidence was raised. The validator's draw was the coordinator's draw call for call.

One step did not run: before its own results count, a validator reruns 10 of the arena's reference answers on its card. This run passed no reference answers to that step, so it checked 0 of them. The 40 miner calls above do not depend on that step.

## 3. The two pool payout

### The reference

The system pool compares each system's cost and p95 latency with a reference: the arena's first baseline model, `claude-haiku-5-5`, answering each of the 50 original system items directly through the relay. The coordinator measures it and posts the answers in its signed report.

- **First pass, 2026-11-19 03:25 UTC.** All 50 frontier calls were refused by the provider, because the relay's account had run out of credit. The coordinator still posted its reference as complete, with no system answers in it. The validator's first grade (08:39 UTC) therefore had no reference, and both systems scored 0 although they met three floors.
- **Remeasured, 10:55 UTC.** The epoch's end was moved later and the coordinator reran the 50 answers: 50 of 50 answered, none empty, 514,816 micros in total (6,668 to 15,308 per item) and a p95 latency of 14,506.9 ms. It posted them in a new signed report (report 7 of the epoch's `spotcheck` document).
- **Regraded, from 11:12 UTC.** The validator regraded the whole epoch from the start and took 250 reference answers from the coordinator: 100 specialist model, 100 base model and 50 system.

The coordinator now retries missing frontier answers and never posts a pool's reference unless every answer is in, and the relay reports the provider's reason when a frontier call fails.

### Pool scores

From the validator's report (`GET /v2/arenas/ctx_compress-granite/epochs/0/reports/5Epocha7…`), the same figures as the settled ledger:

| UID | Specialist model | Items passed | System | Floors met (value) |
|---|---|---|---|---|
| 14 | 0.8626, rank 1 | 47 of 50 (lower bound 0.8378) | 0.3869, rank 1 | 0.80 (0.511), 0.90 (0.519), 0.95 (0.517); not 0.99 |
| 1 | 0.3491, rank 2 | 24 of 50 (lower bound 0.3480) | 0.3688, rank 2 | 0.80 (0.488), 0.90 (0.493), 0.95 (0.494); not 0.99 |

The system figures at each floor, against the reference of 50 answers, 514,816 micros and a p95 of 14,506.9 ms:

| UID | Pass rate | Lower bound | Cost (99 items) | p95 latency | Escalated |
|---|---|---|---|---|---|
| 14 | 1.00 | 0.9734 | 609,194 to 610,063 micros | 182.5 to 193.1 ms | 100% |
| 1 | 1.00 | 0.9734 | 621,482 micros | 210.1 to 220.4 ms | 100% |

### What the systems did

- Neither entry submitted a router. Without one, each entry's harness gives its own answer a fixed confidence below the lowest floor, so it sent every system item to escalation. The report shows 100% escalated.
- Every escalation call was refused for the same reason as the first reference pass: 1,582 of 1,584 calls, and the other 2 returned an empty answer. When the frontier returns nothing, the escalation path keeps the harness's own answer, so every system answer that was graded is the entry's local answer.
- Those answers passed every item at every floor (99 of 99), a one sided lower bound of 0.9734 (z 1.645). That meets the floors 0.80, 0.90 and 0.95 and misses 0.99, which 99 items cannot reach.
- Their cost is the entries' own model tokens.

### Payout

The settled ledger (`GET /v2/arenas/ctx_compress-granite/epochs/0/ledger`, computed 2026-11-19 13:27:52 UTC):

| UID | Specialist model pool (60%) | System pool (40%) | Share of miner emission |
|---|---|---|---|
| 14 | rank 1: 61.54% of the pool | rank 1: 61.54% of the pool | 61.54% |
| 1 | rank 2: 38.46% of the pool | rank 2: 38.46% of the pool | 38.46% |
| 0 (owner, burn) | | | 0% |

- With two eligible entries per pool, the rank payout 40% and 25% renormalises to 61.54% and 38.46%.
- Both entries were spot checked, and the quorum was the one reporting validator.
- UID 16 set these weights at block 8,479,341 (`0.615384615` and `0.384615385`), and sends them again every chain epoch.
- The chain's incentive matched them from block 8,479,704 (14:31 UTC), one chain epoch after the commit, as commit reveal delays it: UID 14 0.6154, UID 1 0.3846, UID 0 0.0. At block 8,479,663 (14:23 UTC) it was still the earlier split, 0.3692, 0.2308 and 0.4.
- Earlier the same day, before the reference was remeasured, the same validator's weights were 36.92%, 23.08% and 40% burned: the specialist model pool paid and the system pool had no reference.

### Under the corrected rules

Three scoring changes ship in mechanism 0.10.0, for the next epoch ([#238](https://github.com/microtensor-io/microtensor-subnet/pull/238), [#239](https://github.com/microtensor-io/microtensor-subnet/pull/239)):

- A system's latency now counts the model's own time: for each model call, the measured p95 time to first token plus the p95 time per output token. Validators answer model calls from the transcript, so the replay alone took about 0.2 s per item while the reference was timed for real.
- Models are priced by nominal size. `ibm-granite/granite-4.0-h-micro` has 3,191,396,096 parameters and was priced in the 8B class; the 3B class now runs to 5B.
- Cost is compared per item. A system floor runs all 99 items (50 originals and 49 twins) while the reference answers the 50 originals, so totals charged the systems for about twice the items.

The same two entries, scored with the merged code (`dc79065`) on their real rows, the coordinator's measured speeds and this reference:

| UID | System score | p95 latency | Cost per item | Reference |
|---|---|---|---|---|
| 14 | 0.2878 | 12,784.5 ms | 3,077 micros | 14,506.9 ms, 10,296 micros |
| 1 | 0.1599 | 45,165.7 ms | 3,139 micros | 14,506.9 ms, 10,296 micros |

Both would still be paid from the system pool: cheaper than the reference by more than three times, and UID 14 faster as well.

## 4. Separate records

- `ctx_compress` epoch 0 settled on 2026-11-05 and stays archived as it settled: its entries, scores, certificates and payout are in [testnet_576](../../testnet_576/README.md) and at `GET /v2/arenas/ctx_compress/epochs/0`.
- `ctx_compress-granite` is a separate arena with its own settings: 50 items in each pool, its own windows and its own epoch 0 at `GET /v2/arenas/ctx_compress-granite/epochs/0`. Nothing from the old arena was renamed, reopened or overwritten.

## Limits

- Two entries were graded, and one validator graded them, so every result rests on its report alone.
- The validator's own spot check covered one miner of this epoch.
- The fail closed cases ran the validator's code offline on the archived epoch's documents, not on a live epoch where a miner went unchecked.
- This is testnet. Testnet stake and emission have no market value.
