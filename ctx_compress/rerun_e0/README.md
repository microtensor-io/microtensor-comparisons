# ctx_compress rerun_e0: checking epoch 0 scores without the coordinator

Arena: `ctx_compress` on Bittensor testnet, epoch 0 (settled 2026-11-05).

**Status: complete, 2026-11-10.** 49 of 49 rerun calls matched the coordinator's record byte for byte, on a rented RTX 4090 with nothing of ours installed, in 38.7 minutes.

## Question

Can someone with a rented 24 GB GPU, nothing of ours installed and only public inputs, rerun the calls our coordinator spot checked in epoch 0 and get the same output, byte for byte?

## What is checked

For each miner, the coordinator drew 40 model calls from the miner's transcript, reran them on an RTX 4090 and published that all 40 matched. The draw is seeded by the transcript's hash and the hash of the chain block 10 blocks after the upload, so anyone can redraw it.

This rerun takes the same draw and reruns every drawn call whose prompt can be rebuilt from public inputs alone: the SLM pool calls and the bare `B0` calls, where the model sees the item directly. The other drawn calls go through the miner's own harness, and rebuilding their prompts means running the miner's code in a sandbox, which this check leaves out.

Each rerun output is compared with the output recorded in the miner's transcript, as token ids and text together. The coordinator does not publish its own output for calls that matched; its signed report states that its rerun reproduced the recorded output. So the coordinator's hash in the table is the hash of the recorded output it reports matching.

## Public inputs only

| Input | Where it comes from | Checked against |
|---|---|---|
| Arena settings: prompt template, engine image, token limits, spot check size | `ctx_compress/arena.yaml` in [microtensor-arenas](https://github.com/microtensor-io/microtensor-arenas) at commit `b7d0244` | |
| Epoch items | `GET /v2/arenas/ctx_compress/epochs/0/inputs/bundle` | `bundle_sha256` in the signed inputs document |
| Miner transcripts | `GET /v2/mirror/<transcript sha256>` | the transcript hash in the epoch's upload list |
| The coordinator's results | the signed `spotcheck` document of epoch 0 | |
| Weights | each miner's own Hugging Face repo at the committed revision, listed in the epoch's `mirror` document | every file's SHA-256, and the weights hash the miner was scored under |
| Draw seed | block hash from a public testnet node | |
| Engine | `vllm/vllm-openai@sha256:6ee133356d49ed24cee03dd0cda3d3980279a11c107ce3e752c89e76540f41c9`, the amd64 image of the public `v0.32.0` tag | |

API base: `https://api.microtensor.cloud`. Testnet node: `https://test.finney.opentensor.ai`.

## Engine settings

The arena's P1 profile, as the coordinator runs it:

```
vllm serve --model <weights dir> --served-model-name slm --max-model-len 125952 \
  --seed 0 --gpu-memory-utilization 0.9 --max-num-seqs 1 --dtype bfloat16 \
  --max-logprobs 1 --no-enable-prefix-caching
```

Each call is a streamed `/v1/completions` request with the recorded prompt, `max_tokens`, stop strings and seed, temperature 0, `logprobs` 1 and `return_token_ids`. Calls run one at a time.

## Steps

1. Rent one GPU with 24 GB or more and a driver for CUDA 13, running the engine image above. Use an RTX 4090 to expect byte for byte matches: the coordinator's card is an RTX 4090, and a different card type can change the arithmetic.
2. In the container:

   ```
   mkdir -p /work && cd /work
   curl -fsSLO https://raw.githubusercontent.com/microtensor-io/microtensor-comparisons/main/ctx_compress/rerun_e0/rerun.py
   python3 rerun.py plan --arena-ref b7d0244 --out plan.json
   python3 rerun.py run --plan plan.json --out out --models models
   ```

3. `plan` downloads the public inputs, checks every hash, redraws the coordinator's 40 calls per miner and rebuilds the prompts. It prints, per miner, whether the redraw contains every call the coordinator timed (those are listed in its report) and how many prompts match the recorded prompt hash. It needs no GPU.
4. `run` downloads each miner's weights, checks them, starts the engine, reruns the calls and writes `out/results.csv` and `out/summary.json`.

`runpod.py` starts the same thing on a RunPod pod (`RUNPOD_API_KEY` in the environment; `up`, `status <id>`, `down <id>`). It is a convenience; nothing in the check depends on it.

## Results

**49 of 49 calls matched byte for byte on the first run.** No call needed a rerun. RunPod community RTX 4090, driver 580.142, CUDA 13.0, vLLM 0.32.0, PyTorch 2.13.0. The whole run took 38.7 minutes, including downloading all four models from Hugging Face without a token.

| Miner | Weights | Calls rerun | Matched | Coordinator's spot check |
|---|---|---|---|---|
| `5DewpgAD…` (A9Labs) | `84b5d274…` | 12 | 12 | 40 of 40 |
| `5FJC3RQ7…` (Tang-yin-112) | `506b500a…` | 18 | 18 | 40 of 40 |
| `5HEtPjha…` (Samonte, epoch 0 winner) | `e7528c49…` | 8 | 8 | 40 of 40 |
| `5DfMHBFP…` (Daniel01410) | `b0bd36e4…` | 11 | 11 | 40 of 40 |

For every miner, the redraw from public data was the coordinator's own draw: it contained every call the coordinator lists as timed. Every rebuilt prompt matched the prompt hash in the transcript, and every weight file matched its committed hash.

### An earlier pass on the same card

An earlier pass of the same check, on the same pod an hour before, matched 45 of 49. All four misses were calls of one model (`b0bd36e4…`), and each output went off course partway through: at tokens 77, 90, 323 and 328 of 590 to 828. The engine log showed the same settings and backends as for the other models. In the final pass all four matched. So this model's outputs can differ between runs on the same card. The other three models gave identical outputs in both passes.

This is why the script reruns a mismatched call once after restarting the engine, which is what the coordinator does before it treats a mismatch as evidence. The earlier pass ran without that step; its files are in `results/first_pass/`.

### What this shows and what it does not

- Anyone can redraw the coordinator's sample and rebuild the prompts from public inputs, and on the same card type get the recorded outputs back.
- The check covers the calls where the model sees the item directly: 49 of the 160 drawn calls. The harness calls need the miner's code run in a sandbox, which this kit does not do.
- It does not show that another card type gives the same bytes. That needs a separate run.
- The coordinator's hash column is the hash of the output recorded in the miner's transcript. The coordinator does not publish its own output for calls that matched.

## Files

| File | Contents |
|---|---|
| `rerun.py` | The whole check: `plan` and `run` |
| `runpod.py` | Starts the check on a RunPod pod |
| `results/results.csv` | One row per call: miner, item, model hash, our output hash, the recorded output hash, match, output tokens, first differing token, seconds, and the retry columns |
| `results/summary.json` | Totals, card, driver, versions, timings, the script's own hash, and per miner the seed block, its hash and the draw check |
| `results/rerun.log` | The run's own log |
| `results/nvidia-smi.txt` | The card the run used |
| `results/engine_logs/` | vLLM's log for each model |
| `results/first_pass/` | The earlier pass: 45 of 49, without the retry step |

`summary.json` records `script_sha256` `cad01247…`, the hash of `rerun.py` in this folder.
