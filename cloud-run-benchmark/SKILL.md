---
name: cloud-run-benchmark
description: Use this skill to benchmark Cloud Run storage performance (GCS, NFS, cache, or synthetic I/O). Supports robust verification, JSON reporting, and resource cleanup. Ideal for validating architecture decisions before production.
---

# Cloud Run Benchmark Skill

This skill provides a **robust, verifiable workflow** for benchmarking storage performance on Google Cloud Run. It automates the lifecycle of testing: Verification -> Deployment -> Benchmarking -> Reporting -> Cleanup.

## Core Capabilities

1.  **Storage Testing**: Compare GCS Fuse, Direct VPC, and NFS.
2.  **Synthetic Benchmarking**: Test maximum container I/O using synthetic data generator (no external files needed).
3.  **Robust Reporting**: Generates JSON & Markdown reports for auditability.
4.  **Auto-Cleanup**: Ensures no expensive resources are left running.

## Benchmarking Workflow

### 1. Build Loader Image
First, ensure the benchmark container image is available:

```bash
bash scripts/build_loader.sh
```

### 2. Run Benchmark
Use the unified `benchmark_cloud_run.sh` script.

#### Scenario A: Synthetic I/O Test (No Dependencies)
Test raw container throughput without bucket/model dependencies.
```bash
bash scripts/benchmark_cloud_run.sh \
  --service-name=bench-synthetic \
  --synthetic \
  --size-gb=10 \
  --cpu=4 --memory=8Gi
```

#### Scenario B: Real Model Loading (GCS + Direct VPC)
Test actual model loading performance.
```bash
bash scripts/benchmark_cloud_run.sh \
  --type=gcs-vpc \
  --bucket=MY_BUCKET \
  --vpc=gpu-vpc \
  --model-file=models/llama-3-70b
```

#### Scenario C: NFS Performance
Test Cloud Filestore throughput.
```bash
bash scripts/benchmark_cloud_run.sh \
  --type=nfs \
  --nfs-ip=10.0.0.2 \
  --file-share=model_share \
  --vpc=gpu-vpc
```

## Configuration Reference

| Flag | Description | Default |
| :--- | :--- | :--- |
| `--type` | `gcs`, `gcs-vpc`, `nfs` (Ignored if `--synthetic`) | `gcs` |
| `--synthetic` | Generate data in-memory instead of reading files | `false` |
| `--size-gb` | Size of synthetic data to generate | `10` |
| `--no-cleanup` | Skip deleting service after test (for debugging) | `false` |
| `--gpu` | Number of GPUs (0 to disable) | `0` |

## Advanced Patterns

For detailed architecture trade-offs and optimization techniques (e.g., chunk sizing, thread counts), see:
[Storage Patterns](references/storage_patterns.md)

## Self-Iteration & Troubleshooting

*   **Low Throughput?**: Check `references/storage_patterns.md` for "Direct VPC" and "Multi-threaded Loading".
*   **Deployment Failed?**: Check `benchmark_run.log` for authentication or quota errors.
*   **Zonal Errors?**: If using GPU, try specifying `--gpu-type` or check `gcloud run regions list`.
