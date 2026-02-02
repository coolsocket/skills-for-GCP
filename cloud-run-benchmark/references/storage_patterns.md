# Cloud Run Storage Patterns & Best Practices

This document records proven strategies for high-performance data loading on Cloud Run, specifically for AI models and large datasets.

## 1. Storage Architecture Comparison

| Architecture | Throughput (Est.) | Latency | Stability | Cost | Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **GCS FUSE (Standard)** | ~50-100 MB/s | High | High | Low (Pay-per-use) | Web assets, small config files, low-budget services. |
| **GCS + Direct VPC** | **~400-500 MB/s** | Medium | High | Low + VPC egress fees | **Cost-effective AI Inference**. Best balance of speed/cost. |
| **Cloud Filestore (NFS)** | **~700-1200 MB/s** | Very Low | **Very High** | High ($200+/mo min) | **Mission-critical AI**. Low cold-start latency requirements. |
| **Anywhere Cache** | Varies (Hit/Miss) | Low (Hit) | Variable | Medium (Cache fees) | Frequent reads of same data across many instances. |

## 2. Optimization Techniques

### Direct VPC Egress
*   **Mechanism**: Forces traffic through Google's private VPC network rather than public internet/gateways.
*   **Benefit**: Reduces network hops and congestion.
*   **Config**: `--vpc-egress=all-traffic` (Requires Private Google Access on Subnet).

### Multi-threaded Loading (Pipeline)
*   **Problem**: `gcsfuse` is often single-threaded or latency-bound on serial reads.
*   **Solution**: Use a Producer-Consumer pattern in Python.
*   **Implementation**:
    *   **Producer**: `ThreadPoolExecutor(max_workers=4)` reads chunks from file(s) into a `Queue`.
    *   **Consumer**: Main thread reads from `Queue` and moves data to GPU/Memory.
*   **Impact**: Increases GCS throughput from ~100MB/s to ~500MB/s (with Direct VPC).

### Chunk Size
*   **Recommendation**: 100MB - 1GB chunks for large models.
*   **Reason**: Reduces overhead of Python function calls and queue locking.

## 3. Troubleshooting & Gotchas

### Zonal Redundancy & GPU Quota
*   **Issue**: Cloud Run defaults to multi-zone redundancy. GPU quota is often specific to a single zone (e.g., `us-central1-a`).
*   **Fix**: Use `--no-gpu-zonal-redundancy` to pinpoint deployment to available zones.

### Private Google Access
*   **Issue**: When using `--vpc-egress=all-traffic`, access to GCS (public API) fails.
*   **Fix**: Enable "Private Google Access" on the VPC Subnet. This bridges VPC internal traffic to Google APIs.

### NFS Mounting
*   **Issue**: `gcloud beta run deploy` flags for NFS often change or break.
*   **Fix**: Use `location` parameter in `gcloud alpha`: `--add-volume=type=nfs,location=IP:/SHARE`.
