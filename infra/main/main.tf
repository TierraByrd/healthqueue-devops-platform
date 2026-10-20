locals {
  common_tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "opentofu"
  }
}

# ─── S3: appointment audit log bucket ────────────────────────────────────────

resource "aws_s3_bucket" "audit_logs" {
  bucket = "${var.project}-audit-logs-${var.environment}"
  tags   = local.common_tags
}

resource "aws_s3_bucket_versioning" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ─── DynamoDB: appointments table ─────────────────────────────────────────────

resource "aws_dynamodb_table" "appointments" {
  name         = "${var.project}-appointments-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "appointment_id"

  attribute {
    name = "appointment_id"
    type = "S"
  }

  tags = local.common_tags
}

# ─── SQS: appointment reminders queue + dead-letter queue ────────────────────

resource "aws_sqs_queue" "reminders_dlq" {
  name                      = "${var.project}-reminders-dlq-${var.environment}"
  message_retention_seconds = var.reminders_dlq_retention_seconds
  tags                      = local.common_tags
}

resource "aws_sqs_queue" "reminders" {
  name = "${var.project}-reminders-${var.environment}"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.reminders_dlq.arn
    maxReceiveCount     = var.reminders_max_receive_count
  })

  tags = local.common_tags
}
