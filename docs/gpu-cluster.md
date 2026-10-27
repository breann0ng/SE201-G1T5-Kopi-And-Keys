# SCIS GPU setup for Kopi & Keys

GPU preparation branch: `feat/gpu-cluster-inference`, 27 October 2026.
The application defaults to CPU. `KOPI_OLLAMA_DEVICE=gpu` opts into Ollama's
automatic offload onto scheduler-visible GPUs. No cluster benchmark result is
claimed until a real allocation, driver and loaded model have been checked.

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
The notebook setup requested 4 CPU cores / 12 GB **system RAM**; GPU VRAM is separate.
Loading a very large model can also hit the job's CPU RAM or storage quota.

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

First verify the runtime with the existing 3B model. Then compare 32B or 27B on
the same GPU. A 122B run is a later experiment if the confirmed allocation fits it;
parameter count alone does not establish better HDB policy answers.

## Start an approved Ollama runtime inside the GPU job

Use a current cluster-approved Ollama installation with Blackwell-capable CUDA
support and support for the chosen model. Check [Ollama hardware support](https://docs.ollama.com/gpu).
Do not install system drivers or services on a shared node.
If `command -v ollama` returns nothing, establish the approved installation/module
method before downloading models. The official Linux archive can be installed
into a permitted user directory instead of a system directory; its documented
layout contains `bin/ollama` and `lib/ollama`.
See the [official Linux installation guide](https://docs.ollama.com/linux).

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
It does not submit a GPU job, install software, or download any model.

From another terminal in the same allocation, start small:

```bash
ollama pull qwen2.5:3b
ollama run qwen2.5:3b 'Reply with the single word READY.'
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
ssh -N -J USER@LOGIN_HOST -L 11435:127.0.0.1:11434 USER@ALLOCATED_COMPUTE_HOST
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
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
.\.venv\Scripts\python.exe -m kopi_keys.evaluation.synthesis_benchmark --device gpu --models qwen2.5:3b qwen2.5:32b --case-ids SYN-01 SYN-02 SYN-09 --output .local/reports/gpu-smoke.json
```

Pull each selected model on the allocated server first; do not download it onto
the laptop by mistake. After a successful smoke run, omit `--case-ids` for all 12
development cases and use `--repeats 3` for a stronger timing comparison.

The GPU benchmark checks the selected loaded model's reported `size_vram` after
warm-up. A CPU fallback stops setup and leaves `completed: false`. Reports retain
the loading record, device request, context/output limits and per-case outcomes.
Keep partial offload distinct from full-GPU measurements. No GPU performance
numbers have been measured by the local mocked tests.

For the full application, restart the backend after setting those variables.
The embedding client also uses `KOPI_OLLAMA_BASE_URL`, so the remote server needs
`embeddinggemma` as well, or hybrid retrieval can fall back to keywords. Keep the
same embedding model as the existing Chroma collection; changing the model needs
a deliberate re-index. SQLite, the local Chroma files and React can stay on the laptop.
For initial synthesis benchmarks, fixed evidence avoids that retrieval dependency.

When finished, stop model serving and cancel only your own notebook job, using
the job ID printed by `mynotebook`. Save reports before a preemption/session expiry.
