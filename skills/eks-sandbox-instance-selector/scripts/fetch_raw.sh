#!/usr/bin/env bash
# Refresh raw inputs for build_data.py. Usage: fetch_raw.sh [region ...]
# Default: the commercial Regions that need no opt-in. Pass Regions to refresh only those;
# build_data.py then updates just those Regions in data/data.json and keeps the others.
# Writes <skill>/raw/types-<region>.json (when the Region can be read) and price-raw-<region>.json.
# Read-only AWS calls: ec2 DescribeInstanceTypes and pricing GetProducts (Linux, shared tenancy, on-demand).
# Instance specs don't differ by Region, so a Region that isn't enabled in the account (DescribeInstanceTypes
# fails) still gets its prices; its types take their specs from the other Regions.
set -euo pipefail
RAW="$(cd "$(dirname "$0")/.." && pwd)/raw"; mkdir -p "$RAW"
REGIONS=("$@"); [ $# -eq 0 ] && REGIONS=(
  us-east-1 us-east-2 us-west-1 us-west-2 ca-central-1 sa-east-1
  eu-central-1 eu-north-1 eu-west-1 eu-west-2 eu-west-3
  ap-northeast-1 ap-northeast-2 ap-northeast-3 ap-south-1 ap-southeast-1 ap-southeast-2)
for r in "${REGIONS[@]}"; do
  echo "== $r: instance types" >&2
  if ! aws ec2 describe-instance-types --region "$r" --output json --query 'InstanceTypes[].{
    t: InstanceType, v: VCpuInfo.DefaultVCpus, c: VCpuInfo.DefaultCores, tpc: VCpuInfo.DefaultThreadsPerCore,
    m: MemoryInfo.SizeInMiB, a: ProcessorInfo.SupportedArchitectures,
    eni: NetworkInfo.MaximumNetworkInterfaces, ip: NetworkInfo.Ipv4AddressesPerInterface,
    bm: BareMetal, hv: Hypervisor}' > "$RAW/types-$r.json.tmp"; then
    rm -f "$RAW/types-$r.json.tmp"
    echo "   skipped: can't read instance types in $r (Region not enabled?); prices only" >&2
  else
    mv "$RAW/types-$r.json.tmp" "$RAW/types-$r.json"
  fi
  echo "== $r: on-demand prices (Pricing API, us-east-1)" >&2
  aws pricing get-products --region us-east-1 --service-code AmazonEC2 --output json --filters \
    Type=TERM_MATCH,Field=regionCode,Value="$r" \
    Type=TERM_MATCH,Field=operatingSystem,Value=Linux \
    Type=TERM_MATCH,Field=tenancy,Value=Shared \
    Type=TERM_MATCH,Field=preInstalledSw,Value=NA \
    Type=TERM_MATCH,Field=capacitystatus,Value=Used \
    Type=TERM_MATCH,Field=licenseModel,Value="No License required" > "$RAW/price-raw-$r.json"
done
echo "done -> $RAW ; next: python3 scripts/build_data.py" >&2
