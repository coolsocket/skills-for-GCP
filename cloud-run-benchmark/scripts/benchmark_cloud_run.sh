#!/bin/bash
# benchmark_cloud_run.sh
# Robust Cloud Run Benchmark Workflow
# Implements: Verification, Deployment, Benchmarking, Reporting, Cleanup

set -u

# --- Configuration ---
LOG_FILE="benchmark_run.log"
REPORT_FILE="benchmark_report.json"
REPORT_MD="benchmark_report.md"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Defaults
PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
SERVICE_NAME="benchmark-${TIMESTAMP}"
IMAGE_URI="gcr.io/${PROJECT_ID}/gpu-model-loader:latest"
CPU="4" 
MEMORY="8Gi" 
GPU="0" # Default no GPU for generic test
GPU_TYPE=""
VPC_NAME=""
SUBNET=""
BUCKET_NAME=""
NFS_IP=""
FILE_SHARE=""
MODEL_FILE="model.bin"
MOUNT_PATH="/mnt/data"
TYPE="gcs"
CLEANUP="true"
USE_SYNTHETIC="false"
SYNTHETIC_SIZE_GB="10"

# --- Logging Helper ---
log() {
    local level=$1
    shift
    local msg="$*"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [${level}] ${msg}" | tee -a "${LOG_FILE}"
}

# --- Cleanup Trap ---
cleanup() {
    if [ "$CLEANUP" == "true" ]; then
        log "INFO" "Cleaning up resources..."
        if gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
            gcloud run services delete "${SERVICE_NAME}" --region "${REGION}" --project "${PROJECT_ID}" --quiet >> "${LOG_FILE}" 2>&1
            log "INFO" "Deleted service: ${SERVICE_NAME}"
        else
            log "INFO" "Service ${SERVICE_NAME} not found or already deleted."
        fi
    else
        log "WARN" "Skipping cleanup as requested (--no-cleanup). Service ${SERVICE_NAME} remains active."
    fi
}
trap cleanup EXIT

# --- Argument Parsing ---
for i in "$@"; do
case $i in
    --type=*) TYPE="${i#*=}" ;;
    --project=*) PROJECT_ID="${i#*=}" ;;
    --region=*) REGION="${i#*=}" ;;
    --service-name=*) SERVICE_NAME="${i#*=}" ;;
    --image=*) IMAGE_URI="${i#*=}" ;;
    --cpu=*) CPU="${i#*=}" ;;
    --memory=*) MEMORY="${i#*=}" ;;
    --gpu=*) GPU="${i#*=}" ;;
    --gpu-type=*) GPU_TYPE="${i#*=}" ;;
    --vpc=*) VPC_NAME="${i#*=}" ;;
    --subnet=*) SUBNET="${i#*=}" ;;
    --bucket=*) BUCKET_NAME="${i#*=}" ;;
    --nfs-ip=*) NFS_IP="${i#*=}" ;;
    --file-share=*) FILE_SHARE="${i#*=}" ;;
    --model-file=*) MODEL_FILE="${i#*=}" ;;
    --synthetic) USE_SYNTHETIC="true" ;;
    --size-gb=*) SYNTHETIC_SIZE_GB="${i#*=}" ;;
    --no-cleanup) CLEANUP="false" ;;
    *) log "ERROR" "Unknown option: $i"; exit 1 ;;
esac
done

# --- 1. Verification Phase ---
log "INFO" "=== Phase 1: Verification ==="
log "INFO" "Project: ${PROJECT_ID}"
log "INFO" "Region: ${REGION}"

if [ -z "$PROJECT_ID" ]; then
    log "ERROR" "No project ID detected. Run 'gcloud config set project ID'."
    exit 1
fi

# Type Logic
ENV_VARS="MOUNT_PATH=${MOUNT_PATH},MODEL_FILE=${MODEL_FILE},USE_SYNTHETIC=${USE_SYNTHETIC},SYNTHETIC_SIZE_GB=${SYNTHETIC_SIZE_GB},PYTHONUNBUFFERED=True"
VOL_FLAGS=""

if [ "$TYPE" == "gcs" ] || [ "$TYPE" == "gcs-vpc" ]; then
    if [ -z "$BUCKET_NAME" ] && [ "$USE_SYNTHETIC" == "false" ]; then
        log "ERROR" "--bucket is required for GCS unless --synthetic is used (actually GCS mount needs bucket regardless)"
        exit 1
    fi
    # GCS Mount is needed even for synthetic if we want to test GCS write/read? 
    # Or just generic container benchmark?
    # If generic, we don't need volumes.
    if [ ! -z "$BUCKET_NAME" ]; then
        VOL_FLAGS="--add-volume=name=gcs-vol,type=cloud-storage,bucket=${BUCKET_NAME} --add-volume-mount=volume=gcs-vol,mount-path=${MOUNT_PATH}"
    fi
elif [ "$TYPE" == "nfs" ]; then
    if [ -z "$NFS_IP" ]; then log "ERROR" "--nfs-ip required for NFS"; exit 1; fi
     VOL_FLAGS="--add-volume=name=nfs-vol,type=nfs,location=${NFS_IP}:/${FILE_SHARE},readonly=true --add-volume-mount=volume=nfs-vol,mount-path=${MOUNT_PATH}"
fi

# VPC Logic
if [ "$TYPE" == "gcs-vpc" ] || [ "$TYPE" == "nfs" ] || [ ! -z "$VPC_NAME" ]; then
    if [ -z "$VPC_NAME" ]; then VPC_NAME="default"; fi 
    VOL_FLAGS="${VOL_FLAGS} --network=${VPC_NAME} --vpc-egress=all-traffic"
    if [ ! -z "$SUBNET" ]; then VOL_FLAGS="${VOL_FLAGS} --subnet=${SUBNET}"; fi
fi

# GPU Logic
GPU_FLAGS=""
if [ "$GPU" != "0" ] && [ ! -z "$GPU_TYPE" ]; then
    GPU_FLAGS="--gpu ${GPU} --gpu-type ${GPU_TYPE} --no-gpu-zonal-redundancy"
fi

# --- 2. Deployment Phase ---
log "INFO" "=== Phase 2: Deployment ==="
CMD="gcloud alpha run deploy ${SERVICE_NAME} \
  --image ${IMAGE_URI} \
  --project ${PROJECT_ID} \
  --region ${REGION} \
  --cpu ${CPU} \
  --memory ${MEMORY} \
  --timeout=3600 \
  --concurrency 4 \
  --max-instances 1 \
  --min-instances 1 \
  --allow-unauthenticated \
  --no-cpu-throttling \
  ${GPU_FLAGS} \
  ${VOL_FLAGS} \
  --set-env-vars=\"${ENV_VARS}\" \
  --format='value(status.url)'"

log "INFO" "Deploying service..."
SERVICE_URL=$(eval $CMD 2>> "${LOG_FILE}")

if [ -z "$SERVICE_URL" ]; then
    log "ERROR" "Deployment failed. Check ${LOG_FILE} for details."
    exit 1
fi
log "INFO" "Service deployed at: ${SERVICE_URL}"

# --- 3. Benchmark Phase ---
log "INFO" "=== Phase 3: Benchmarking ==="

# Trigger Start
log "INFO" "Triggering benchmark..."
START_RESP=$(curl -s -X POST "${SERVICE_URL}/start" -H "Content-Type: application/json" -d "{\"synthetic_size_gb\": ${SYNTHETIC_SIZE_GB}}")
log "INFO" "Start Response: ${START_RESP}"

# Poll
log "INFO" "Polling for completion..."
STATUS="running"
ATTEMPTS=0
MAX_ATTEMPTS=120 # 10 minutes (5s interval)

while [ "${STATUS}" == "running" ] || [ "${STATUS}" == "idle" ]; do
    if [ $ATTEMPTS -gt $MAX_ATTEMPTS ]; then
        log "ERROR" "Timeout waiting for benchmark."
        break
    fi
    
    sleep 5
    REPORT=$(curl -s "${SERVICE_URL}/report")
    STATUS=$(echo "${REPORT}" | grep -o '"status": *"[^"]*"' | cut -d'"' -f4)
    SPEED=$(echo "${REPORT}" | grep -o '"throughput_mb_s": *[0-9.]*' | cut -d: -f2 | tr -d ' ')
    
    log "INFO" "Status: ${STATUS} | current speed: ${SPEED} MB/s"
    ATTEMPTS=$((ATTEMPTS+1))
    
    if [ "${STATUS}" == "completed" ] || [ "${STATUS}" == "error" ]; then
        break
    fi
done

# --- 4. Reporting Phase ---
log "INFO" "=== Phase 4: Reporting ==="
echo "${REPORT}" > "${REPORT_FILE}"
log "INFO" "Saved raw report to ${REPORT_FILE}"

# Generate MD
SPEED_VAL=$(echo "${REPORT}" | grep -o '"throughput_mb_s": *[0-9.]*' | cut -d: -f2 | tr -d ' ')
DURATION_VAL=$(echo "${REPORT}" | grep -o '"duration_sec": *[0-9.]*' | cut -d: -f2 | tr -d ' ')

cat <<EOF > "${REPORT_MD}"
# Cloud Run Benchmark Report

- **Date**: $(date)
- **Service**: ${SERVICE_NAME}
- **Type**: ${TYPE}
- **Resources**: CPU=${CPU}, Mem=${MEMORY}, GPU=${GPU}
- **Throughput**: **${SPEED_VAL} MB/s**
- **Duration**: ${DURATION_VAL} s

## Configuration
- Synthetic: ${USE_SYNTHETIC} (${SYNTHETIC_SIZE_GB} GB)
- Mount: ${MOUNT_PATH}
- Project: ${PROJECT_ID}
EOF

log "INFO" "Generated summary at ${REPORT_MD}"
cat "${REPORT_MD}"

log "INFO" "Benchmark Workflow Complete."
