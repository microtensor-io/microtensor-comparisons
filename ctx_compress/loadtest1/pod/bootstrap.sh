#!/usr/bin/env bash
set -euo pipefail

SUBNET_REF="${SUBNET_REF:-main}"
RAW="${RAW:-https://raw.githubusercontent.com/microtensor-io/microtensor-comparisons/main/ctx_compress/loadtest1/pod}"
SERVER="${MT_SERVER_URL:-https://api.microtensor.cloud}"
GATEWAY="${MT_GATEWAY_URL:-wss://api.microtensor.cloud/v1/operators/socket}"
MODEL="${MT_MODEL:-mt/ctx_compress}"
PIN="${MT_PIN:-}"
LABEL="${MT_LABEL:-loadtest 4090}"
WORKER="${MT_WORKER:-pod}"
export MT_WALLET_PATH=/root/.bittensor/wallets
export PYTHONUNBUFFERED=1

mkdir -p /work /data /opt/system "$MT_WALLET_PATH"
exec > >(tee -a /work/log.txt) 2>&1
echo "==> $(date -u +%FT%TZ) bootstrap on $(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
(cd /work && python3 -m http.server 8070 --bind 0.0.0.0 >/dev/null 2>&1 &)
(while true; do curl -fs http://127.0.0.1:8000/metrics -o /work/vllm.tmp 2>/dev/null && mv /work/vllm.tmp /work/vllm.prom; sleep 5; done &)
(while true; do echo "$(date -u +%FT%TZ),$(nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits)" >> /work/gpu.csv; sleep 5; done &)

echo "==> packages"
apt-get update -qq >/dev/null 2>&1 || true
apt-get install -y -qq git >/dev/null 2>&1 || true
pip install -q "git+https://github.com/microtensor-io/microtensor-subnet@${SUBNET_REF}" 2>&1 | tail -3
python3 -c "import vllm, microtensor_subnet; print('vllm', vllm.__version__)"

echo "==> system"
curl -fsSL "$RAW/prepare.py" -o /work/prepare.py
MT_SERVER_URL="$SERVER" MT_MODEL="$MODEL" python3 /work/prepare.py

echo "==> shim"
(MT_SHIM_WORKERS=${MT_SHIM_WORKERS:-16} MT_SYSTEM_DIR=/opt/system MT_SHIM_BIND=127.0.0.1 MT_SHIM_PORT=8800 mt-shim --request-seconds 300 > /work/shim.log 2>&1 &)
for _ in $(seq 1 240); do
  if curl -fs http://127.0.0.1:8800/health >/dev/null 2>&1; then break; fi
  sleep 5
done
curl -s http://127.0.0.1:8800/health; echo

echo "==> wallet"
python3 - <<'EOF'
import os
from bittensor_wallet import Keypair, Wallet
w = Wallet(name="loadtest", hotkey="default", path="/root/.bittensor/wallets")
if not w.hotkey_file.exists_on_device():
    public = os.environ.get("MT_COLDKEY_SS58", "").strip()
    if public:
        w.set_coldkeypub(Keypair(ss58_address=public), encrypt=False, overwrite=True)
    else:
        w.create_new_coldkey(n_words=12, use_password=False, overwrite=False, suppress=True)
    words = os.environ.get("MT_HOTKEY_MNEMONIC", "").strip()
    if words:
        w.regenerate_hotkey(mnemonic=words, use_password=False, overwrite=True, suppress=True)
    else:
        w.create_new_hotkey(n_words=12, use_password=False, overwrite=False, suppress=True)
print("hotkey", w.hotkey.ss58_address)
EOF

echo "==> register"
mt operator register --label "$LABEL" --server "$SERVER" --wallet-name loadtest --wallet-hotkey default --wallet-path "$MT_WALLET_PATH" || true

echo "==> run"
if [ -z "$PIN" ]; then
  PIN="$(curl -fsSL "$SERVER/v1/public/inference/catalogue" | python3 -c "import json,sys; d=json.load(sys.stdin); print(next(m['pin'] for m in d['models'] if m['model']=='$MODEL'))")"
fi
echo "pin $PIN"
exec mt operator run --serve "$PIN" --shim-url "0=http://127.0.0.1:8800" --gpus 0 --worker "$WORKER" \
  --home /data --server "$SERVER" --gateway "$GATEWAY" --no-auto-update --request-seconds 300 --max-concurrency ${MT_SHIM_WORKERS:-16} \
  --wallet-name loadtest --wallet-hotkey default --wallet-path "$MT_WALLET_PATH"
