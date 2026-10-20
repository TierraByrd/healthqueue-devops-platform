# ─── S3 audit logs ───────────────────────────────────────────────────────────

output "audit_logs_bucket_name" {
  description = "Name of the S3 bucket used for appointment audit logs."
  value       = aws_s3_bucket.audit_logs.id
}

output "audit_logs_bucket_arn" {
  description = "ARN of the audit-log S3 bucket."
  value       = aws_s3_bucket.audit_logs.arn
}

# ─── DynamoDB appointments table ─────────────────────────────────────────────

output "appointments_table_name" {
  description = "Name of the DynamoDB appointments table."
  value       = aws_dynamodb_table.appointments.name
}

output "appointments_table_arn" {
  description = "ARN of the DynamoDB appointments table."
  value       = aws_dynamodb_table.appointments.arn
}

# ─── SQS reminders queue ─────────────────────────────────────────────────────

output "reminders_queue_url" {
  description = "URL of the SQS appointment reminders queue."
  value       = aws_sqs_queue.reminders.url
}

output "reminders_queue_arn" {
  description = "ARN of the SQS appointment reminders queue."
  value       = aws_sqs_queue.reminders.arn
}

output "reminders_dlq_url" {
  description = "URL of the SQS reminders dead-letter queue."
  value       = aws_sqs_queue.reminders_dlq.url
}

output "reminders_dlq_arn" {
  description = "ARN of the SQS reminders dead-letter queue."
  value       = aws_sqs_queue.reminders_dlq.arn
}
