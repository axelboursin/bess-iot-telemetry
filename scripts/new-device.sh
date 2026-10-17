#!/usr/bin/env bash
# Generate a device key pair and a certificate signing request (CSR).
#
# The private key is created locally (in production: on the device itself or
# in its secure element) and never leaves it. Terraform only receives the CSR,
# so no private key ever lands in the Terraform state.
#
# Usage: scripts/new-device.sh <site-id>
set -euo pipefail

site_id="${1:?usage: $0 <site-id>}"
if [[ ! "$site_id" =~ ^[a-z0-9-]{3,64}$ ]]; then
  echo "site-id must match ^[a-z0-9-]{3,64}$" >&2
  exit 1
fi

dir="$(cd "$(dirname "$0")/.." && pwd)/devices"
mkdir -p "$dir"
key="$dir/$site_id.key"
csr="$dir/$site_id.csr.pem"

if [[ -e "$key" ]]; then
  echo "$key already exists, refusing to overwrite" >&2
  exit 1
fi

# ECDSA P-256 is supported by AWS IoT Core and cheap for constrained devices.
openssl ecparam -name prime256v1 -genkey -noout -out "$key"
chmod 600 "$key"
openssl req -new -key "$key" -subj "/CN=$site_id" -out "$csr"

cat <<EOF
Created:
  $key      (secret, git-ignored)
  $csr  (public, commit it)

Next:
  1. Add "$site_id" to var.sites in terraform/environments/*.tfvars
  2. Apply Terraform, then fetch the certificate:
       terraform -chdir=terraform output -json device_certificates_pem \\
         | jq -r '.["$site_id"]' > devices/$site_id.crt
EOF
