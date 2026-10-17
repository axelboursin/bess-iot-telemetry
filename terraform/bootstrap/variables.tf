variable "project" {
  description = "Must match var.project of the main stack."
  type        = string
  default     = "bess"
}

variable "aws_region" {
  type    = string
  default = "eu-west-3"
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the roles, as owner/name."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use the owner/name format."
  }
}
