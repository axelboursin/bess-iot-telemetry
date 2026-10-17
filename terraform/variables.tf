variable "project" {
  description = "Short project name, used as a prefix for every resource."
  type        = string
  default     = "bess"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.project))
    error_message = "project must be lowercase alphanumeric with dashes, 2-16 characters."
  }
}

variable "environment" {
  description = "Deployment environment (dev, prod...)."
  type        = string
}

variable "aws_region" {
  description = "AWS region hosting IoT Core and the data lake."
  type        = string
  default     = "eu-west-3"
}

variable "repository" {
  description = "Source repository, recorded as a tag on every resource."
  type        = string
  default     = "unknown"
}

variable "sites" {
  description = "Site IDs to register as IoT things. Each needs devices/<site>.csr.pem."
  type        = set(string)
  default     = []

  validation {
    condition     = alltrue([for s in var.sites : can(regex("^[a-z0-9-]{3,64}$", s))])
    error_message = "Site IDs must match ^[a-z0-9-]{3,64}$."
  }
}

variable "raw_retention_days" {
  description = "Days before raw telemetry objects expire."
  type        = number
  default     = 365
}

variable "athena_bytes_scanned_cutoff" {
  description = "Per-query scan limit for the Athena workgroup (cost guard)."
  type        = number
  default     = 1073741824 # 1 GiB
}
