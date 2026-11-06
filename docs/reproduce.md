# Reproduce ctx_compress exp1

Every step below can be run on its own. Steps 1 and 2 rebuild the dataset. Step 4 regrades the summaries we saved, so you can check our grades without a GPU. Steps 3 and 5 rerun the models.

All commands run from the root of this repository.

## What you need

| For | You need |
|---|---|
| Rebuilding the items (steps 1, 2) | Python 3.11, git |
| Regrading (step 4) | Docker, 4 CPU cores, about 4 GB of disk |
| Rerunning the local models (step 3) | Docker with one NVIDIA GPU of 24 GB (we used an RTX 4090), about 30 GB of disk, a Hugging Face account with access to the three archived models |
| Rerunning the frontier contestants, reader and judge (step 5) | An API key for an OpenAI compatible chat API that serves the models |
| Analysis (step 6) | Python 3.11 |

## 1. Install

The arena format, renderer and label builder live in the public arenas repository. Install it from a checkout, because it reads the arena folders from there.

```bash
git clone https://github.com/microtensor-io/microtensor-comparisons
git clone https://github.com/microtensor-io/microtensor-arenas
git -C microtensor-arenas checkout 47d5c34993ff8291c889f4fbbdb8c2b5b598e043

cd microtensor-comparisons
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e "../microtensor-arenas[compress]"
pip install -r requirements.txt
export PYTHONPATH=$PWD
```

## 2. Build the dataset

Fetch the study's package at the commit we used, generate Set A with its own generator, download Set B and verify the hashes, then build the items.

```bash
mkdir -p sources
git clone https://github.com/felixwoolford/compaction-study-replication sources/compaction-study-replication
git -C sources/compaction-study-replication checkout 8c7c35f5d3222909c1ac8ef4bc44f90ba6a61512

python -I tools/gen_set_a.py sources/compaction-study-replication sources/setA
python -I tools/fetch_set_b.py sources/compaction-study-replication sources/setB

python -m comparisons.items \
  --package sources/compaction-study-replication \
  --set-a sources/setA --set-b sources/setB \
  --out ctx_compress/exp1/data

mta check ctx_compress/exp1/data
sha256sum ctx_compress/exp1/data/items.jsonl
```

Expected:

- `gen_set_a.py` prints 18 lines, each with 17 facts and 3 lures.
- `fetch_set_b.py` ends with `18 of 18 verified`.
- `mta check` prints `36 items, 0 problems`.
- The SHA-256 is `c61e850fe00c50237a7be1e21e43f1c1acfa545e66ac66f693a56e41036a877a`.

`tools/gen_set_a.py` writes only the plant phase and round 1 of each session, which is the session as it stood at the study's first compaction. The token counts need the Granite tokenizer, which downloads from Hugging Face on first use.

## 3. Run the local models

Get the weights. M1, M2 and M3 are gated: open each repo on Hugging Face, request access, then log in.

```bash
huggingface-cli login
huggingface-cli download microtensor-io/ctx_compress-e7528c49 --local-dir models/M1
huggingface-cli download microtensor-io/ctx_compress-b0bd36e4 --local-dir models/M2
huggingface-cli download microtensor-io/ctx_compress-84b5d274 --local-dir models/M3
huggingface-cli download ibm-granite/granite-4.0-h-micro \
  --revision d5f01a3ea75f088947be3aae039f4ad52837dfde --local-dir models/B0
```

The model files sit at the root of each archive repo. The `system/` and `training/` folders in it are the miner's harness and training code and are not used here.

Run one model at a time. Start the arena's pinned engine with the arena's settings, run the 36 items, stop the engine, then move to the next model.

```bash
docker run --rm -d --name engine --gpus all -p 8000:8000 \
  -e HF_HUB_OFFLINE=1 -e VLLM_NO_USAGE_STATS=1 \
  -v $PWD/models/M1:/model:ro \
  vllm/vllm-openai@sha256:6ee133356d49ed24cee03dd0cda3d3980279a11c107ce3e752c89e76540f41c9 \
  --model /model --served-model-name slm --port 8000 --host 0.0.0.0 \
  --max-model-len 125952 --seed 0 --gpu-memory-utilization 0.9 \
  --max-num-seqs 1 --dtype bfloat16 --max-logprobs 1 --no-enable-prefix-caching

python -m comparisons.run engine --contestant M1 --card "RTX 4090"

docker stop engine
```

Repeat with `M2`, `M3` and `B0`, changing the mounted folder and `--contestant`. Each run writes `ctx_compress/exp1/results/work/outputs/<ID>.jsonl` and skips items that are already there, so delete our file first if you want a clean rerun.

Notes:

- The runner sends the arena's prompt template with the item's system and user text, temperature 0, at most 3,072 tokens, the arena's stop string and seed 0. It makes one short warm up call first and then runs the items one after another.
- Outputs are deterministic for a given card and image. On a different GPU model the text can differ in places.
- Our published times were measured next to the engine on the same machine. If you run the engine on another host, your times include the network.

## 4. Grade

The grader is the arena's own, from the public subnet repository. The simplest way to run it with the right dependencies is inside the public validator image. Continuation probes are answered by a small model on a pinned llama.cpp server.

```bash
docker network create comparisons

docker run --rm --network comparisons --entrypoint python \
  -e PYTHONPATH=/work -e RUN_CACHE=/work/.cache -v $PWD:/work -w /work \
  ghcr.io/microtensor-io/validator:1 -m comparisons.grade prepare

docker run -d --name probe --network comparisons --cpus 4 \
  -v $PWD/.cache/probe/Qwen__Qwen2.5-1.5B-Instruct-GGUF/91cad51170dc346986eccefdc2dd33a9da36ead9:/model:ro \
  ghcr.io/ggml-org/llama.cpp@sha256:43b3988c22c00faae3d04a8f6e3eba41403dff7c5f5952490599f1bcbdc6f3c2 \
  -m /model/qwen2.5-1.5b-instruct-q8_0.gguf --host 0.0.0.0 --port 8000 --alias slm \
  -t 4 -tb 4 -c 8192 -np 1 --cache-reuse 256

rm -f ctx_compress/exp1/results/work/graded/*.jsonl

docker run --rm --network comparisons --entrypoint python \
  -e PYTHONPATH=/work -e RUN_CACHE=/work/.cache -e PROBE_URL=http://probe:8000 \
  -v $PWD:/work -w /work \
  ghcr.io/microtensor-io/validator:1 -m comparisons.grade M1 M2 M3 B0

docker rm -f probe
```

`prepare` downloads the probe model and the tokenizer into `.cache` and prints the server command above. Grading writes `results/work/graded/<ID>.jsonl`, one row per item with the format check, token count, recall, hallucination, the probe model's answers, the item score and the pass flag.

By default the probe model is only asked about summaries that can score (all nine headings and within budget). Set `-e SCORED_ONLY=0` to ask it about every summary. On 4 CPU cores a scorable summary takes about one minute; the four local models took about 50 minutes in total.

To check our grades without rerunning any model, run this step on the outputs already in the repository and compare the new `graded` files with ours.

## 5. Frontier contestants, reader and judge

These go through any OpenAI compatible chat API. The model names in `comparisons/prompts.py` map to provider model ids (`LIST_PRICES`); change them there if your provider names them differently.

```bash
export OPENROUTER_API_KEY=...        # or use --key-env and --endpoint for another provider

python -m comparisons.jobs summaries --pi sources/pi-package/package
python -m comparisons.run jobs --jobs ctx_compress/exp1/results/work/summaries.jobs.jsonl
python -m comparisons.jobs collect
```

`--pi` points at the extracted Pi package (`npm pack @earendil-works/pi-coding-agent@1.1.0`, then extract the archive into `sources/pi-package`). It is only read for the two prompt strings used by contestant P1, which we also saved in `results/work/pi_prompt.json`.

Grade the four new contestants as in step 4 (`... -m comparisons.grade F1 F2 F3 P1`), then run the study's probes and the judge:

```bash
python -m comparisons.jobs reader --package sources/compaction-study-replication
python -m comparisons.run jobs --jobs ctx_compress/exp1/results/work/reader.jobs.jsonl --workers 8

python -m comparisons.jobs judge --package sources/compaction-study-replication
python -m comparisons.run jobs --jobs ctx_compress/exp1/results/work/judge.jobs.jsonl
```

The reader step needs the summaries of all eight summarising contestants. It asks one question per call: 360 planted fact and lure questions and 27 commitment probes for each of the ten contestants. The judge step packs the commitment replies in a shuffled order with no contestant names, asks for three votes each, and sends a random quarter to a second judge.

Expected cost at list prices is about 95 USD in total, most of it the reader on the full sessions (contestant C1).

We have not run this step yet, so it is the least tested part of the repository.

## 6. Analyse

```bash
python -m comparisons.analyse --package sources/compaction-study-replication
python -m comparisons.document --public --link
python -m comparisons.charts
```

`analyse` writes `raw.jsonl`, `summary.csv`, `tests.csv`, `chart.png`, `hand_check.md` and `analysis.json` into `ctx_compress/exp1/results/`. It works with whatever has been run so far and marks the rest as not run. `document` writes `comparison.json`, the document the Models page reads. `charts` draws the four charts in `results/charts/` from those files.

With only the local models run, `summary.csv` must match the one in this repository.
