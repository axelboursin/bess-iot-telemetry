output "bucket_name" {
  value = aws_s3_bucket.lake.bucket
}

output "kms_key_arn" {
  value = aws_kms_key.lake.arn
}

output "firehose_stream_name" {
  value = aws_kinesis_firehose_delivery_stream.telemetry.name
}

output "athena_workgroup" {
  value = aws_athena_workgroup.telemetry.name
}

output "athena_table" {
  value = "${aws_glue_catalog_database.telemetry.name}.${aws_glue_catalog_table.raw.name}"
}
