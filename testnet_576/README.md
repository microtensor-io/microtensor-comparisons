# Testnet results: subnet 576

Covered: 2026-11-01 to 2026-11-18. Network: Bittensor testnet, netuid 576.

**Status: complete for this period.** Every figure comes from the public results API (`https://api.microtensor.cloud/v2/...`) and the testnet chain (`wss://test.finney.opentensor.ai:443`).

## Short answer

- **Epochs.** One evaluation epoch has run and settled: `ctx_compress` epoch 0, from 2026-11-01 to 2026-11-05. The next epoch was withdrawn, and its public record is empty. Since then the arena has been closed and paying the epoch 0 result. A second arena, `doc_parse`, is defined but has not opened. On the chain this period spans about 342 chain epochs (tempo 360 blocks, about 72 minutes each).
- **Miners.** 18 UIDs are registered: the owner, 2 validators and 15 miners. 11 hotkeys entered epoch 0. 10 entries were mirrored, and 4 evaluation jobs were run and graded. All 4 matched their spot checks, 40 of 40 calls each.
- **Validators.** One validator graded epoch 0 and set the weights: UID 16. A second validator, UID 4, last set weights on 2026-10-28, before the epoch opened, and has set none since. A coordinator key with no stake ran the spot checks and signed the certificates.
- **Specialist model pool.** All 4 graded entries were eligible and paid, with scores 0.8708, 0.8675, 0.7108 and 0.2026.
- **System pool.** No entry scored above 0, so the pool was burned. One entry missed every floor, one met two floors but earned no value against the reference, and two were duplicates.
- **Weights.** Not during epoch 0. No validator set weights from 2026-11-01 until 2026-11-05 11:03 UTC, three hours after the epoch closed, and the chain showed no miner incentive in that time. Since then UID 16 has set weights 261 times, in every chain epoch but one, and the chain has paid the settled split at every daily sample from 2026-11-05 13:24 UTC.

## Terms

- **Specialist model:** the small fine tuned model an entry submits.
- **Harness:** code around the model that prepares the prompt and checks or repairs the output.
- **Router:** a small classifier that predicts whether the specialist model will pass an item.
- **Escalation:** the rule that sends hard items on to a frontier model.
- **System:** the specialist model, harness, router and escalation working together.
- **Pools:** each part is scored and paid in its own pool, alongside a serving share for providers that serve the certified models.
- **Mirrored:** the entry's model files were copied from Hugging Face so validators can load them.
- **Spot check:** a second run of a sample of a job's calls, to confirm the job's answers.

## Epochs

| Arena | Epoch | Opened | Commits closed | Closed | Settled | Result |
|---|---|---|---|---|---|---|
| `ctx_compress` | 0 | 2026-11-01 09:01 UTC (block 8,348,450) | 2026-11-03 11:37 UTC (8,363,631) | 2026-11-05 08:03 UTC (8,376,963) | 2026-11-05 12:12 UTC | 11 entered, 4 graded, settled |
| `ctx_compress` | 1 | Planned start 2026-11-05 14:03 UTC (8,378,764) | | | | Withdrawn; public record empty (no batch, no submissions) |
| `doc_parse` | | | | | | Draft, never opened |

`ctx_compress` is agent session compaction: a small model writes the summary an agent loads to keep working. The base model is `ibm-granite/granite-4.0-h-micro`. In epoch 0 the specialist model, system, harness and escalation pools each used 25 hidden items, and the router pool used 60.

## Miners

| UID | Commit | Mirrored | Job rows graded | Spot check | Specialist model | System | Other pools | Certificate |
|---|---|---|---|---|---|---|---|---|
| 2 | Sealed | Yes | 200 | 40 of 40 | 0.8708, rank 1 | 0 | | Yes |
| 13 | Open | Yes | 250 | 40 of 40 | 0.8675, rank 2 | 0, duplicate | Duplicates | Yes |
| 14 | Open | Yes | 250 | 40 of 40 | 0.7108, rank 3 | 0, duplicate | Duplicates | Yes |
| 1 | Open | Yes | 250 | 40 of 40 | 0.2026, rank 4 | 0 | Harness 0.1986, rank 1; escalation 0.508, rank 1 | Yes |
| 6, 7, 8, 9, 10 | Sealed | Yes | No job uploaded | | | | | |
| 15 | Open | Yes | No job uploaded | | | | | |
| 12 | Open | No, repository not found | | | | | | |

- A job row is one hidden item run through one submitted part, so the count depends on what the entry submitted. UID 2 entered no harness or escalation, so it had 200 rows rather than 250.
- The 11 hotkeys came from 6 Hugging Face accounts. 6 commits were sealed and revealed, and 5 were open.
- UIDs 3, 5, 11 and 17 are registered but did not enter.
- **Duplicates.** The validator sets a pool row to 0 when the part is identical to an earlier entry's:
  - the harness, escalation and system parts of UIDs 13 and 14 duplicated UID 1's;
  - UID 15's model weights were identical to UID 13's, and its other parts duplicated UID 1's.
- No evidence of cheating was posted and nobody was banned.
- The certified entries are archived on Hugging Face under `microtensor-io/ctx_compress-<hash>`.

## Validators

| UID | Stake in epoch 0 (epoch validator list) | Role in epoch 0 | Weights |
|---|---|---|---|
| 16 | 650 | Filed the only report, 2026-11-05 11:03 UTC: all 11 entries covered, the 4 with jobs graded | Every chain epoch but one since 2026-11-05 11:03 UTC |
| 4 | 7,730 | Received the sealed keys; filed no report | Last set 2026-10-28 13:01 UTC, all to the owner UID; none since |
| Coordinator, no UID | 0 | Spot checked the 4 jobs (complete 2026-11-05 08:30 UTC) and signed the 4 certificates | Does not set weights |

With one report, UID 16 alone made the quorum for every result.

## Pool scores

### Specialist model pool

| Rank | UID | Items passed | Score | Share of the pool |
|---|---|---|---|---|
| 1 | 2 | 25 of 25 | 0.8708 | 43.5% |
| 2 | 13 | 25 of 25 | 0.8675 | 27.2% |
| 3 | 14 | 22 of 25 | 0.7108 | 16.3% |
| 4 | 1 | 9 of 25 | 0.2026 | 13.0% |

How the score is built:

- It starts from the Wilson lower bound of the pass rate (z 1.96), so 25 of 25 passes gives 0.867.
- That is multiplied by three gates: provenance (the model must match its declared base and beat it), the hardware envelope, and twin items.
- It is then multiplied by a small efficiency bonus.
- An item passes at an item score of 0.60.

### System pool

| UID | Pass rate | Score | Why |
|---|---|---|---|
| 2 | 0.92 | 0 | Its lower bound, 0.785, is below the lowest floor, 0.80 |
| 1 | 1.00 at floors 0.80 and 0.90; 0.72 at 0.95 and 0.99 | 0 | It met floors 0.80 and 0.90, but its value at each was 0: the value weighs answer cost and p95 latency against the frontier reference, and its p95 latency was 58 to 61 s against the reference's 15 s |
| 13, 14 | | 0 | Duplicate of UID 1 |

How the system pool is scored:

- A system is scored at four quality floors: 0.80, 0.90, 0.95 and 0.99.
- At each floor it earns value only if the lower bound of its pass rate reaches the floor. This pool uses a one sided bound (z 1.645), so 25 of 25 gives 0.902 and 23 of 25 gives 0.785.
- The value at a floor compares the system's answer cost and p95 latency with the frontier reference.
- With no entry above 0, the system pool was burned.

### Other pools

UID 1 won the harness pool (0.1986) and the escalation pool (0.508) alone. The router pool had no entries.

## Payout and weights

The settled split below is what UID 16 set as its weights. The chain's incentive matches it at every daily sample from 2026-11-05 13:24 UTC.

| UID | Share of miner emission | From |
|---|---|---|
| 0 (subnet owner, burn) | 46.0% | The serving share (10%), because no provider earned a serving score, plus the router and system pools (18% each), which had no eligible entry. The chain burns emission sent to the owner UID |
| 1 | 38.3% | Specialist model rank 4, harness, escalation |
| 2 | 7.8% | Specialist model rank 1 |
| 13 | 4.9% | Specialist model rank 2 |
| 14 | 2.9% | Specialist model rank 3 |

- 90% of miner emission goes to the five modelling pools, 18% each, and 10% to serving.
- Within a pool, the top five get 40%, 25%, 15%, 12% and 8%, renormalised over the eligible entries.

## Weight setting per chain epoch

How it was measured:

- The chain's record of when each UID last set weights was read every 360 blocks, from block 8,348,450 to 8,472,005.
- Weights and incentive were sampled daily.
- Commit reveal is on for this subnet, with a reveal period of one chain epoch, so weights take effect after they are set. That is why incentive first appeared after 12:12 UTC on 2026-11-05.

| Period | Chain epochs | Weights set | Miner incentive on the chain |
|---|---|---|---|
| 2026-11-01 09:01 to 2026-11-05 11:03 UTC, from the opening of epoch 0 to its report | about 81 | None. UID 4's last weights, from 2026-10-28, were older than the chain's activity cutoff of 5,000 blocks | None at any sample |
| 2026-11-05 11:03 to 2026-11-18 12:47 UTC | about 261 | By UID 16, 261 updates, in every chain epoch but one. Median spacing 351 blocks. The one gap was 735 blocks (11:03 to 13:30 UTC on 2026-11-05), which skipped the chain epoch from about 11:16 to 12:28 UTC | The settled split at every daily sample from 2026-11-05 13:24 UTC; the 12:12 UTC sample was still empty |

Only UIDs 4 and 16 have ever set weights on this subnet. UID 16 registered on 2026-11-05 at 00:18 UTC and first set weights when it filed its epoch 0 report.

## Limits

- One epoch with 4 graded entries and 25 items in each scored pool is a small sample.
- One validator graded every entry, so every result rests on its report alone.
- The 11 entrants came from 6 accounts, so fewer independent teams took part than hotkeys.
- This is testnet. Testnet stake and emission have no market value.
