#!/usr/bin/env bash
# Run inside your assigned SCIS GPU job, after loading an approved Ollama runtime.
set -euo pipefail

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    echo 'No Slurm allocation found. Start a GPU notebook/job first; do not serve models on the login node.' >&2
    exit 1
fi
if [[ -z "${CUDA_VISIBLE_DEVICES:-}" || "${CUDA_VISIBLE_DEVICES}" == '-1' ]]; then
    echo 'No scheduler-visible GPU found. Check your GPU allocation; do not override CUDA_VISIBLE_DEVICES.' >&2
    exit 1
fi
command -v nvidia-smi >/dev/null || { echo 'nvidia-smi is unavailable in this job.' >&2; exit 1; }
if ! command -v ollama >/dev/null && [[ -x /common/public/ollama/bin/ollama ]]; then
    export PATH="/common/public/ollama/bin:$PATH"
fi
command -v ollama >/dev/null || { echo 'Load an approved Ollama installation first.' >&2; exit 1; }
: "${OLLAMA_MODELS:?Set OLLAMA_MODELS to your approved project/scratch model directory first.}"

mkdir -p -- "$OLLAMA_MODELS"
nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv
df -h -- "$OLLAMA_MODELS"
if [[ -z "${KOPI_CLUSTER_OLLAMA_PORT:-}" ]]; then
    KOPI_CLUSTER_OLLAMA_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
fi
if [[ ! "$KOPI_CLUSTER_OLLAMA_PORT" =~ ^[0-9]+$ ]] || (( KOPI_CLUSTER_OLLAMA_PORT < 1024 || KOPI_CLUSTER_OLLAMA_PORT > 65535 )); then
    echo 'KOPI_CLUSTER_OLLAMA_PORT must be an unprivileged TCP port.' >&2
    exit 1
fi
export OLLAMA_HOST="127.0.0.1:${KOPI_CLUSTER_OLLAMA_PORT}"
export OLLAMA_NO_CLOUD=1
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
echo "Starting Ollama within job $SLURM_JOB_ID on $(hostname) at http://$OLLAMA_HOST, loopback only."
exec ollama serve
