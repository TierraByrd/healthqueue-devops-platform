variable "project" {
  description = "Project name; used in resource names and tags."
  type        = string
  default     = "healthqueue"
}

variable "environment" {
  description = "Deployment environment (dev | staging | prod)."
  type        = string
  default     = "dev"
}
