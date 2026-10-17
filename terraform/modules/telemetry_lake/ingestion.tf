# IoT Core rule -> Kinesis Data Firehose -> S3 (GZIP JSON lines, partitioned by day)

resource "aws_cloudwatch_log_group" "ingestion" {
  name              = "/${var.name}/telemetry-ingestion"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_stream" "firehose" {
  name           = "firehose-s3-delivery"
  log_group_name = aws_cloudwatch_log_group.ingestion.name
}

# Firehose -------------------------------------------------------------------

data "aws_iam_policy_document" "firehose_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["firehose.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "firehose" {
  name               = "${var.name}-telemetry-firehose"
  assume_role_policy = data.aws_iam_policy_document.firehose_assume.json
}

data "aws_iam_policy_document" "firehose" {
  statement {
    sid = "WriteToLake"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetBucketLocation",
      "s3:ListBucket",
      "s3:ListBucketMultipartUploads",
      "s3:PutObject",
    ]
    resources = [aws_s3_bucket.lake.arn, "${aws_s3_bucket.lake.arn}/*"]
  }

  statement {
    sid       = "EncryptWithLakeKey"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [aws_kms_key.lake.arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${local.region}.amazonaws.com"]
    }
  }

  statement {
    sid       = "DeliveryErrorLogs"
    actions   = ["logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingestion.arn}:*"]
  }
}

resource "aws_iam_role_policy" "firehose" {
  name   = "deliver-to-s3"
  role   = aws_iam_role.firehose.id
  policy = data.aws_iam_policy_document.firehose.json
}

resource "aws_kinesis_firehose_delivery_stream" "telemetry" {
  name        = "${var.name}-telemetry"
  destination = "extended_s3"

  server_side_encryption {
    enabled  = true
    key_type = "AWS_OWNED_CMK"
  }

  extended_s3_configuration {
    role_arn            = aws_iam_role.firehose.arn
    bucket_arn          = aws_s3_bucket.lake.arn
    prefix              = "telemetry/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/"
    error_output_prefix = "errors/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/"
    buffering_size      = 5
    buffering_interval  = 60
    compression_format  = "GZIP"
    kms_key_arn         = aws_kms_key.lake.arn

    cloudwatch_logging_options {
      enabled         = true
      log_group_name  = aws_cloudwatch_log_group.ingestion.name
      log_stream_name = aws_cloudwatch_log_stream.firehose.name
    }
  }

  depends_on = [aws_iam_role_policy.firehose]
}

# IoT topic rule -------------------------------------------------------------

data "aws_iam_policy_document" "iot_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["iot.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "iot_rule" {
  name               = "${var.name}-telemetry-iot-rule"
  assume_role_policy = data.aws_iam_policy_document.iot_assume.json
}

data "aws_iam_policy_document" "iot_rule" {
  statement {
    sid       = "ForwardToFirehose"
    actions   = ["firehose:PutRecord", "firehose:PutRecordBatch"]
    resources = [aws_kinesis_firehose_delivery_stream.telemetry.arn]
  }

  statement {
    sid       = "RuleErrorLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["${aws_cloudwatch_log_group.ingestion.arn}:*"]
  }
}

resource "aws_iam_role_policy" "iot_rule" {
  name   = "forward-telemetry"
  role   = aws_iam_role.iot_rule.id
  policy = data.aws_iam_policy_document.iot_rule.json
}

resource "aws_iot_topic_rule" "telemetry" {
  name        = "${local.snake_name}_telemetry_to_lake"
  description = "Forward gateway telemetry to the S3 data lake"
  enabled     = true
  sql_version = "2016-03-23"

  # topic(2) is the site ID taken from the topic. The device policy guarantees
  # a gateway can only publish on its own topic, so unlike the payload's
  # site_id this value cannot be spoofed.
  sql = "SELECT *, topic(2) AS topic_site_id, timestamp() AS ingested_at FROM '${var.telemetry_topic_filter}'"

  firehose {
    delivery_stream_name = aws_kinesis_firehose_delivery_stream.telemetry.name
    role_arn             = aws_iam_role.iot_rule.arn
    separator            = "\n"
  }

  error_action {
    cloudwatch_logs {
      log_group_name = aws_cloudwatch_log_group.ingestion.name
      role_arn       = aws_iam_role.iot_rule.arn
    }
  }

  depends_on = [aws_iam_role_policy.iot_rule]
}
