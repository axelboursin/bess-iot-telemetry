# Glue catalog + Athena, using partition projection so new days are queryable
# immediately without crawlers or MSCK REPAIR.

resource "aws_glue_catalog_database" "telemetry" {
  name = "${local.snake_name}_telemetry"
}

resource "aws_glue_catalog_table" "raw" {
  name          = "raw_telemetry"
  database_name = aws_glue_catalog_database.telemetry.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification              = "json"
    compressionType             = "gzip"
    "projection.enabled"        = "true"
    "projection.year.type"      = "integer"
    "projection.year.range"     = "2025,2040"
    "projection.month.type"     = "integer"
    "projection.month.range"    = "1,12"
    "projection.month.digits"   = "2"
    "projection.day.type"       = "integer"
    "projection.day.range"      = "1,31"
    "projection.day.digits"     = "2"
    "storage.location.template" = "s3://${aws_s3_bucket.lake.bucket}/telemetry/year=$${year}/month=$${month}/day=$${day}/"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lake.bucket}/telemetry/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    dynamic "columns" {
      for_each = local.telemetry_columns
      content {
        name    = columns.key
        type    = columns.value.type
        comment = columns.value.comment
      }
    }
  }
}

locals {
  # Mirrors bess_telemetry.messages.build_telemetry + fields added by the IoT rule.
  telemetry_columns = {
    schema_version      = { type = "int", comment = "Payload schema version" }
    site_id             = { type = "string", comment = "Site ID declared by the gateway" }
    ts                  = { type = "string", comment = "Measurement time, ISO 8601 UTC" }
    soc_pct             = { type = "double", comment = "State of charge (%)" }
    soh_pct             = { type = "double", comment = "State of health (%)" }
    active_power_kw     = { type = "double", comment = "Active power, positive = discharge (kW)" }
    reactive_power_kvar = { type = "double", comment = "Reactive power (kvar)" }
    temperature_c       = { type = "double", comment = "Battery temperature (degC)" }
    dc_voltage_v        = { type = "double", comment = "DC bus voltage (V)" }
    status              = { type = "int", comment = "0 idle, 1 charging, 2 discharging, 3 fault" }
    topic_site_id       = { type = "string", comment = "Site ID from the MQTT topic (trusted)" }
    ingested_at         = { type = "bigint", comment = "IoT Core receive time, epoch ms" }
  }
}

resource "aws_athena_workgroup" "telemetry" {
  name          = "${var.name}-telemetry"
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_bytes_scanned_cutoff

    result_configuration {
      output_location = "s3://${aws_s3_bucket.lake.bucket}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = aws_kms_key.lake.arn
      }
    }
  }
}

resource "aws_athena_named_query" "latest_per_site" {
  name      = "latest-state-per-site"
  workgroup = aws_athena_workgroup.telemetry.id
  database  = aws_glue_catalog_database.telemetry.name
  query     = <<-SQL
    SELECT topic_site_id, ts, soc_pct, active_power_kw, temperature_c, status
    FROM (
      SELECT *, row_number() OVER (PARTITION BY topic_site_id ORDER BY ingested_at DESC) AS rn
      FROM raw_telemetry
      WHERE year = date_format(current_date, '%Y')
        AND month = date_format(current_date, '%m')
        AND day = date_format(current_date, '%d')
    )
    WHERE rn = 1
  SQL
}

resource "aws_athena_named_query" "hourly_energy" {
  name      = "hourly-energy-throughput"
  workgroup = aws_athena_workgroup.telemetry.id
  database  = aws_glue_catalog_database.telemetry.name
  query     = <<-SQL
    -- Average power over an hour equals energy in kWh for that hour.
    SELECT topic_site_id,
           date_trunc('hour', from_iso8601_timestamp(ts)) AS hour,
           avg(greatest(active_power_kw, 0))  AS discharged_kwh,
           avg(greatest(-active_power_kw, 0)) AS charged_kwh,
           min(soc_pct) AS soc_min,
           max(soc_pct) AS soc_max
    FROM raw_telemetry
    WHERE year = date_format(current_date, '%Y')
      AND month = date_format(current_date, '%m')
    GROUP BY 1, 2
    ORDER BY 1, 2
  SQL
}
