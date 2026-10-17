locals {
  name = "${var.project}-${var.environment}"
}

module "telemetry_lake" {
  source = "./modules/telemetry_lake"

  name                        = local.name
  telemetry_topic_filter      = "bess/+/telemetry"
  raw_retention_days          = var.raw_retention_days
  athena_bytes_scanned_cutoff = var.athena_bytes_scanned_cutoff
}

module "device_fleet" {
  source = "./modules/device_fleet"

  name = local.name
  devices = {
    for site in var.sites : site => {
      csr_pem = file("${path.root}/../devices/${site}.csr.pem")
    }
  }
}
