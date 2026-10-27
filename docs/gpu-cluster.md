# SCIS GPU setup for Kopi & Keys

GPU preparation branch: `feat/gpu-cluster-inference`, 27 October 2026.
The application defaults to CPU. `KOPI_OLLAMA_DEVICE=gpu` opts into Ollama's
automatic offload onto scheduler-visible GPUs. The first measured GPU run is
recorded below; it used the allocated MIG slice, not the entire physical card.

## Request and open the notebook

The verified [cluster notebook instructions](https://violet.scis.dev/docs/Interactive%20jobs/jupyter)
use the interactive `mynotebook` command. Select GPU enabled, then the required GPU
type by its label. In the student's observed menu, option 7 was
`rtx_pro_6000_blackwell_max`; select Python_Only for this Ollama workflow.
Ollama does not require installing PyTorch or TensorFlow in the notebook's Python
environment. The Blackwell menu explicitly requires CUDA 12.8 or newer support.

Wait for the GPU job to run and Jupyter to print its connection instructions.
Package-installation jobs used to create the environment are separate from the
eventual GPU notebook allocation. Interactive notebooks expire after six hours.

Run the printed SSH tunnel command in a **new PowerShell on the laptop**, leaving
it open, then open the full printed browser URL. The notebook URL points at
localhost on the laptop, which works only while the tunnel forwards that port.
Notebook tokens and passwords stay local; do not commit them or paste them into logs.

In the notebook, check the real allocation:

```python
!hostname
!nvidia-smi
!whichgpu
!command -v ollama
!df -h .
```

```python
import os
print({key: os.environ.get(key) for key in (
    "SLURM_JOB_ID", "SLURM_JOB_GPUS", "CUDA_VISIBLE_DEVICES"
)})
```

The supplied inventory lists 48 GB L40S/A40 GPUs and a 96 GB Blackwell node with
undergraduate priority. Its Blackwell row has stale/inconsistent 48 GB L40S tags,
so use the actual allocation and `nvidia-smi`, not that row alone, to size a model.
Total node RAM and the number of installed cards are not your job's allocation.
The environment-setup job requested 4 CPU cores / 12 GB **system RAM**; GPU VRAM is separate.
Loading a very large model can also hit the job's CPU RAM or storage quota.

The first real notebook allocation revealed a **24,192 MiB MIG slice** on the
96 GB Blackwell card, not the entire physical GPU. The allocated notebook job
reported 32 GB host RAM, 4 CPU cores and a `MIG-...` visible-device identifier.
Size models for the slice and preserve that identifier. Do not disable MIG or
switch to a parent GPU. A 72B/122B full-GPU run does not fit this slice.

The [partition guide](https://violet.scis.dev/docs/Getting%20started/partitions)
describes one-GPU student/project quotas. Check your own `myinfo` output; do not
copy a research partition/QoS or request an entire multi-GPU node from an example.
The [GPU selection guide](https://violet.scis.dev/docs/Advanced%20settings/selectGPUs)
documents mandatory `--constraint` and optional `--prefer` selectors, but actual
GPU availability and account permissions still determine allocation.

## Choose a first model and a larger candidate

These are inference candidates with short 4K context and one request at a time,
not guarantees of fit. Weight-file size is not total GPU memory consumption.

| Allocated VRAM | Starting point | Larger experiment |
| --- | --- | --- |
| 11 GB | Qwen2.5 3B / 7B | Check fit before increasing size |
| 24 GB | Qwen2.5 14B | A 27B/32B quantization may be tight after runtime overhead |
| 48 GB | Qwen2.5 32B or Qwen3.5 27B | Keep headroom for context and runtime |
| 96 GB | Qwen2.5 72B | Qwen3.5 122B Q4, after checking free VRAM, CPU RAM and disk quota |
| 141 GB | Qwen3.5 122B Q4 | Availability/access to H200 is not established by the inventory |

Current official model pages list [Qwen2.5 32B](https://ollama.com/library/qwen2.5:32b)
at about 20 GB, [Qwen2.5 72B](https://ollama.com/library/qwen2.5:72b) at 47 GB,
[Qwen3.5 27B Q4](https://ollama.com/library/qwen3.5:27b-q4_K_M) at about 17 GB,
and [Qwen3.5 122B](https://ollama.com/library/qwen3.5:122b) at about 81 GB.
These models do not require per-token API payments when self-hosted. Cluster
allocation, quota, model licensing and storage requirements still apply.
There is no universal largest free model implied by this inventory.

First verify the runtime with a model already available in the approved pool.
Controlled comparisons should run each selected model on the same GPU.
Parameter count alone does not establish better HDB policy answers.

For this observed MIG allocation, the existing shared pool already contains a
tag `qwen3.8:latest` reporting 27.3B, Q4_K_M, about 17.74 GB on disk. It loaded
with a 4K context and reported its whole 17.28 GB loaded footprint in VRAM.
This makes the provided 27B tag a concrete candidate without another download.
The shared tag is recorded as reported by the local server; it is not an assertion
about the identity or quality of the latest upstream Qwen release.

## Start an approved Ollama runtime inside the GPU job

Use a current cluster-approved Ollama installation with Blackwell-capable CUDA
support and support for the chosen model. Check [Ollama hardware support](https://docs.ollama.com/gpu).
Do not install system drivers or services on a shared node.
If `command -v ollama` returns nothing, establish the approved installation/module
method before downloading models. The official Linux archive can be installed
into a permitted user directory instead of a system directory; its documented
layout contains `bin/ollama` and `lib/ollama`.
See the [official Linux installation guide](https://docs.ollama.com/linux).

The existing course notebooks identify `/common/public/ollama/bin/ollama`
(observed version 0.34.2) and `/common/public/ollama/models`. An empty `command -v`
does not mean that binary is absent. The launcher adds this approved binary path
if needed. Reuse models in the shared pool read-only; do not pull/delete shared
models. Downloads require a separate approved writable user/project model directory.

Check available storage and any user/project quota before downloading tens of GB.
Set `OLLAMA_MODELS` to an approved project/scratch directory, not an assumed path.
Upload `scripts/start_cluster_ollama.sh` into Jupyter and run it from a terminal
**inside the assigned GPU job**, for example:

```bash
export OLLAMA_MODELS="/your/approved/model-storage-directory"
bash start_cluster_ollama.sh
```

The launcher refuses missing Slurm/GPU allocation variables, preserves
`CUDA_VISIBLE_DEVICES`, binds only to compute-node loopback, disables Ollama cloud
features, and limits the server to one resident model / one parallel request.
It picks a free local port unless `KOPI_CLUSTER_OLLAMA_PORT` is set, avoiding a
collision with another user's default port. It does not submit a GPU job, install
software, or download any model.

From another terminal in the same allocation, check the available tags:

```bash
# Point this client at the private server's printed port, not another user's server.
export OLLAMA_HOST="127.0.0.1:YOUR_PRINTED_PORT"
export PATH="/common/public/ollama/bin:$PATH"
ollama list
# Pull only when OLLAMA_MODELS is an approved writable user/project directory.
# ollama pull qwen2.5:3b
# Observed shared tag; use an available tag that fits YOUR allocation.
ollama run qwen3.8:latest 'Reply with the single word READY.'
ollama ps
```

Inspect the PROCESSOR column. Some GPU offload is not proof that the entire model
fits; establish `100% GPU` before treating timings as full-GPU results. Capture
GPU type, driver, free VRAM, Ollama version and model tag/digest for the report.
Do not expose unallocated GPUs by changing `CUDA_VISIBLE_DEVICES`.

## Connect the existing app and run the benchmark

The notebook's web tunnel forwards its Jupyter port, not Ollama's port. The model
server remains loopback-only. If cluster policy permits SSH into the assigned
compute job, a separate SSH ProxyJump tunnel can forward the model port:

```powershell
ssh -N -J USER@LOGIN_HOST -L 11435:127.0.0.1:OLLAMA_PORT USER@ALLOCATED_COMPUTE_HOST
```

Replace placeholders with the real login and allocated compute host. Establish
this only for your allocated job; the cluster warns that direct compute-node SSH
can attach to the wrong job when several jobs share an account/node. If that
path is unavailable, run benchmarks inside the allocated notebook instead of
exposing an unauthenticated model server on the network.

With that model tunnel established, in a new local PowerShell:

```powershell
$env:KOPI_OLLAMA_BASE_URL = 'http://127.0.0.1:11435'
$env:KOPI_OLLAMA_DEVICE = 'gpu'
$env:KOPI_EMBED_BASE_URL = 'http://127.0.0.1:11434'
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.synthesis_benchmark --device gpu --models qwen3.8:latest --case-ids SYN-01 SYN-02 SYN-09 --output .local/reports/gpu-smoke.json
```

Use tags already present on the allocated server, or download additional models
only into approved writable storage. After a successful smoke run, omit `--case-ids` for all 12
development cases and use `--repeats 3` for a stronger timing comparison.

The GPU benchmark checks the selected loaded model's reported `size_vram` after
warm-up. A CPU fallback stops setup and leaves `completed: false`. Reports retain
the loading record, device request, context/output limits and per-case outcomes.
Keep partial offload distinct from full-GPU measurements. Mocked tests validate
configuration and failure handling; they do not measure GPU performance.

For the full application, restart the backend after setting those variables.
Set `KOPI_OLLAMA_MODEL` and `KOPI_POLICY_MODEL` to the selected available tag
(for this session, `qwen3.8:latest`). Leave local CPU defaults unchanged in the
committed configuration. Keep local Ollama running for EmbeddingGemma.
The embedding client follows `KOPI_OLLAMA_BASE_URL` unless `KOPI_EMBED_BASE_URL`
overrides it. Use the latter to keep existing EmbeddingGemma retrieval local
without requiring the remote server to have that model. Keep the same embedding
model as the existing Chroma collection; changing the model needs a deliberate
re-index. SQLite, the local Chroma files and React can stay on the laptop.
For initial synthesis benchmarks, fixed evidence avoids that retrieval dependency.

When finished, stop model serving and cancel only your own notebook job, using
the job ID printed by `mynotebook`. Save reports before a preemption/session expiry.

## Observed GPU results, 27 October 2026

The allocated Blackwell MIG slice had 24,192 MiB VRAM, four CPU cores and 32 GB
host RAM. The approved Ollama runtime reported version 0.34.2. The shared
`qwen3.8:latest` tag reported 27.3B Q4_K_M; its 17,278,099,782-byte loaded
footprint equalled its reported VRAM footprint at 4K context.

The same 12 fixed-evidence development cases used for the CPU comparison gave
**11/12 expected-outcome and quote-coverage passes**, ten answered cases, two
correct abstentions and no engine errors. Median wall time was **2.825 seconds**;
the first case took 23.546 seconds. This is one repeat, with human quality review
pending. It is not a held-out policy-accuracy estimate.

The failed coverage check was SYN-08: the question asks for the family loan-income
ceiling, and the model quoted that family condition with its source citation.
The original label also demands extended-family and singles ceilings. That is a
label-review finding; the published score remains 11/12 and labels are unchanged.

The benchmark ran production synthesis/verifier code on the laptop with genuine
remote inference forwarded through the authenticated Jupyter kernel. Wall times
include that bridge and network overhead. Model, runtime and hardware all differ
from the historical CPU run; do not attribute the difference to GPU alone or
claim a controlled model-size comparison.

Three additional in-process application checks used the real hybrid retriever,
local EmbeddingGemma/Chroma and SQLite tool with remote GPU synthesis:

| Question | Result | Wall time |
| --- | --- | --- |
| Can EHG and PHG be combined for first-timer resale families? | Answered, verifier passed | 12.318 s |
| What is the HDB-loan household income ceiling for families? | Answered, verifier passed | 3.363 s |
| Can a Singapore PR couple buy a resale flat? | Answered | 0.202 s |

These are application-graph checks, not browser click-through tests. A curated
[summary JSON](benchmarks/2026-10-27-gpu-summary.json) records settings, outcomes
and limitations. Full raw outputs stay in `.local/reports/`.

After reconnecting the SSH tunnels, the multi-grant question also answered via
HTTP through Vite's `/api/chat` proxy, FastAPI, the direct GPU tunnel and the
verifier in 12.637 seconds. `/api/ps` again reported the entire loaded model
footprint in GPU memory. This checks the frontend/backend proxy path, not a
browser click-through or a fresh independent benchmark.

## Reconnect after closing the laptop

Reconnect the VPN and reopen the printed Jupyter SSH tunnel. If the allocation
and notebook kernel are still alive, do not request a new GPU job or rerun server
setup. Reopen the separate model tunnel using the existing private server port.
An idle model may be unloaded while the server remains alive; the next request
loads it again. If the allocation expired, request a new job and use its newly
printed host, ports and notebook token. Model files and locally saved reports
survive a tunnel disconnect.
