#!/usr/bin/env bash
# Refresh raw inputs for build_data.py. Usage: fetch_raw.sh [region ...]   (default: us-west-2 ap-east-1)
# Writes <skill>/raw/types-<region>.json and price-raw-<region>.json, then run build_data.py.
# Read-only AWS calls: ec2 DescribeInstanceTypes and pricing GetProducts (Linux, shared tenancy, on-demand).
set -euo pipefail
RAW="$(cd "$(dirname "$0")/.." && pwd)/raw"; mkdir -p "$RAW"
REGIONS=("$@"); [ $# -eq 0 ] && REGIONS=(us-west-2 ap-east-1)
for r in "${REGIONS[@]}"; do
  echo "== $r: instance types" >&2
  aws ec2 describe-instance-types --region "$r" --output json --query 'InstanceTypes[].{
    t: InstanceType, v: VCpuInfo.DefaultVCpus, c: VCpuInfo.DefaultCores, tpc: VCpuInfo.DefaultThreadsPerCore,
    m: MemoryInfo.SizeInMiB, a: ProcessorInfo.SupportedArchitectures,
    eni: NetworkInfo.MaximumNetworkInterfaces, ip: NetworkInfo.Ipv4AddressesPerInterface,
    bm: BareMetal, hv: Hypervisor}' > "$RAW/types-$r.json"
  echo "== $r: on-demand prices (Pricing API, us-east-1)" >&2
  aws pricing get-products --region us-east-1 --service-code AmazonEC2 --output json --filters \
    Type=TERM_MATCH,Field=regionCode,Value="$r" \
    Type=TERM_MATCH,Field=operatingSystem,Value=Linux \
    Type=TERM_MATCH,Field=tenancy,Value=Shared \
    Type=TERM_MATCH,Field=preInstalledSw,Value=NA \
    Type=TERM_MATCH,Field=capacitystatus,Value=Used \
    Type=TERM_MATCH,Field=licenseModel,Value="No License required" > "$RAW/price-raw-$r.json"
done
echo "done -> $RAW ; next: uv run --no-project python scripts/build_data.py" >&2
