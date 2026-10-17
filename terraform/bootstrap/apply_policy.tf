# Least-privilege write permissions for the main stack. Every statement is
# scoped to resources named "<project>-*" (or tagged Project=<project>).

locals {
  region  = var.aws_region
  p       = var.project
  p_snake = replace(var.project, "-", "_")
}

data "aws_iam_policy_document" "apply" {
  statement {
    sid     = "IoTCore"
    actions = ["iot:*"]
    resources = [
      "arn:aws:iot:${local.region}:${local.account_id}:thing/*",
      "arn:aws:iot:${local.region}:${local.account_id}:thinggroup/${local.p}-*",
      "arn:aws:iot:${local.region}:${local.account_id}:thingtype/${local.p}-*",
      "arn:aws:iot:${local.region}:${local.account_id}:policy/${local.p}-*",
      "arn:aws:iot:${local.region}:${local.account_id}:cert/*",
      "arn:aws:iot:${local.region}:${local.account_id}:rule/${local.p_snake}_*",
    ]
  }

  statement {
    sid = "IoTAccountLevel"
    actions = [
      "iot:CreateCertificateFromCsr",
      "iot:DescribeEndpoint",
      "iot:ListAttachedPolicies",
      "iot:ListPrincipalThings",
      "iot:ListTagsForResource",
      "iot:ListThingPrincipals",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "Firehose"
    actions   = ["firehose:*"]
    resources = ["arn:aws:firehose:${local.region}:${local.account_id}:deliverystream/${local.p}-*"]
  }

  statement {
    sid     = "S3ProjectBuckets"
    actions = ["s3:*"]
    resources = [
      "arn:aws:s3:::${local.p}-*-telemetry-${local.account_id}",
      "arn:aws:s3:::${local.p}-*-telemetry-${local.account_id}/*",
    ]
  }

  statement {
    sid     = "GlueCatalog"
    actions = ["glue:*"]
    resources = [
      "arn:aws:glue:${local.region}:${local.account_id}:catalog",
      "arn:aws:glue:${local.region}:${local.account_id}:database/${local.p_snake}_*",
      "arn:aws:glue:${local.region}:${local.account_id}:table/${local.p_snake}_*/*",
      "arn:aws:glue:${local.region}:${local.account_id}:userDefinedFunction/${local.p_snake}_*/*",
    ]
  }

  statement {
    sid       = "Athena"
    actions   = ["athena:*"]
    resources = ["arn:aws:athena:${local.region}:${local.account_id}:workgroup/${local.p}-*"]
  }

  statement {
    sid     = "Logs"
    actions = ["logs:*"]
    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/${local.p}-*",
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/${local.p}-*:*",
    ]
  }

  statement {
    sid       = "KmsCreate"
    actions   = ["kms:CreateKey", "kms:TagResource"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = [local.p]
    }
  }

  statement {
    sid       = "KmsManageProjectKeys"
    actions   = ["kms:*"]
    resources = ["arn:aws:kms:${local.region}:${local.account_id}:key/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Project"
      values   = [local.p]
    }
  }

  statement {
    sid     = "KmsAliases"
    actions = ["kms:CreateAlias", "kms:DeleteAlias", "kms:UpdateAlias"]
    resources = [
      "arn:aws:kms:${local.region}:${local.account_id}:alias/${local.p}-*",
      "arn:aws:kms:${local.region}:${local.account_id}:key/*",
    ]
  }

  statement {
    sid = "IamServiceRoles"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:DeleteRolePolicy",
      "iam:PutRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:UpdateRoleDescription",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.p}-*"]
  }

  # The pipeline must never be able to edit its own roles.
  statement {
    sid     = "DenySelfEscalation"
    effect  = "Deny"
    actions = ["iam:*"]
    resources = [
      aws_iam_role.plan.arn,
      aws_iam_role.apply.arn,
    ]
  }

  statement {
    sid       = "PassServiceRoles"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.p}-*"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["iot.amazonaws.com", "firehose.amazonaws.com"]
    }
  }
}
