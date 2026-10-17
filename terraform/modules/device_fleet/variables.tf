variable "name" {
  description = "Prefix for resource names."
  type        = string
}

variable "devices" {
  description = "Map of thing name (site ID) to its certificate signing request."
  type = map(object({
    csr_pem = string
  }))
}
