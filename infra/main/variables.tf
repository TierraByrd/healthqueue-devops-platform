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

variable "reminders_dlq_retention_seconds" {
  description = "How long (seconds) the DLQ retains unprocessed messages."
  type        = number
  default     = 1209600 # 14 days
}

variable "reminders_max_receive_count" {
  description = "Number of delivery attempts before a message is moved to the DLQ."
  type        = number
  default     = 3
}
