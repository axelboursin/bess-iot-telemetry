variable "name" {
  description = "Prefix for resource names."
  type        = string
}

variable "telemetry_topic_filter" {
  description = "MQTT topic filter selecting telemetry messages."
  type        = string
}

variable "raw_retention_days" {
  description = "Days before raw telemetry objects expire."
  type        = number
}

variable "athena_bytes_scanned_cutoff" {
  description = "Per-query scan limit for the Athena workgroup."
  type        = number
}
