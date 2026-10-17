output "iot_endpoint" {
  value = data.aws_iot_endpoint.ats.endpoint_address
}

output "certificates_pem" {
  value = { for site, cert in aws_iot_certificate.site : site => cert.certificate_pem }
}

output "thing_names" {
  value = [for thing in aws_iot_thing.site : thing.name]
}
