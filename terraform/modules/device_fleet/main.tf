data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

data "aws_iot_endpoint" "ats" {
  endpoint_type = "iot:Data-ATS"
}

locals {
  arn_prefix = "arn:aws:iot:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}"
  # IoT policy variable, resolved at connection time to the thing attached to
  # the certificate. Escaped so Terraform does not interpolate it.
  thing = "$${iot:Connection.Thing.ThingName}"
}

resource "aws_iot_thing_type" "bess" {
  name = "${var.name}-bess-gateway"

  properties {
    description = "On-site gateway bridging a battery PMS (Modbus TCP) to the cloud"
  }
}

resource "aws_iot_thing" "site" {
  for_each = var.devices

  name            = each.key
  thing_type_name = aws_iot_thing_type.bess.name
}

# Certificates are issued from a CSR: the private key stays on the device and
# never appears in the Terraform state.
resource "aws_iot_certificate" "site" {
  for_each = var.devices

  csr    = each.value.csr_pem
  active = true
}

resource "aws_iot_thing_principal_attachment" "site" {
  for_each = var.devices

  thing     = aws_iot_thing.site[each.key].name
  principal = aws_iot_certificate.site[each.key].arn
}

# One policy shared by the whole fleet. Policy variables restrict each device
# to its own client ID and topics, so a compromised gateway cannot publish as
# another site or read another site's commands.
data "aws_iam_policy_document" "device" {
  statement {
    sid       = "ConnectAsOwnThing"
    actions   = ["iot:Connect"]
    resources = ["${local.arn_prefix}:client/${local.thing}"]

    condition {
      test     = "Bool"
      variable = "iot:Connection.Thing.IsAttached"
      values   = ["true"]
    }
  }

  statement {
    sid     = "PublishOwnTelemetryAndAcks"
    actions = ["iot:Publish"]
    resources = [
      "${local.arn_prefix}:topic/bess/${local.thing}/telemetry",
      "${local.arn_prefix}:topic/bess/${local.thing}/commands/ack",
    ]
  }

  statement {
    sid       = "SubscribeOwnCommands"
    actions   = ["iot:Subscribe"]
    resources = ["${local.arn_prefix}:topicfilter/bess/${local.thing}/commands"]
  }

  statement {
    sid       = "ReceiveOwnCommands"
    actions   = ["iot:Receive"]
    resources = ["${local.arn_prefix}:topic/bess/${local.thing}/commands"]
  }
}

resource "aws_iot_policy" "device" {
  name   = "${var.name}-bess-gateway"
  policy = data.aws_iam_policy_document.device.json
}

resource "aws_iot_policy_attachment" "site" {
  for_each = var.devices

  policy = aws_iot_policy.device.name
  target = aws_iot_certificate.site[each.key].arn
}
