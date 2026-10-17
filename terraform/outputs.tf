output "iot_endpoint" {
  description = "MQTT endpoint to set as MQTT_HOST on the edge agent (port 8883)."
  value       = module.device_fleet.iot_endpoint
}

output "device_certificates_pem" {
  description = "Certificates issued from each device CSR. Public material, safe to output."
  value       = module.device_fleet.certificates_pem
}

output "telemetry_bucket" {
  value = module.telemetry_lake.bucket_name
}

output "athena_workgroup" {
  value = module.telemetry_lake.athena_workgroup
}

output "athena_table" {
  description = "Fully qualified table to query, e.g. SELECT * FROM <table> WHERE year='2026' LIMIT 10"
  value       = module.telemetry_lake.athena_table
}
