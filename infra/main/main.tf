locals {
  # Consistent tags applied to every resource so cost reports, ownership
  # queries, and compliance audits can filter by project or environment
  # without inspecting resource names.
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
    # Versioning enables point-in-time recovery: a deleted or overwritten
    # audit log object can be restored from a previous version.  For
    # healthcare audit logs this is a regulatory requirement — records must
    # not be silently losable.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id

  rule {
    apply_server_side_encryption_by_default {
      # AES256 (SSE-S3) encrypts audit log data at rest with AWS-managed keys.
      # No key management overhead; satisfies the basic at-rest encryption
      # requirement for appointment (PHI-adjacent) data.
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id

  # All four flags together form a defense-in-depth layer: even if an
  # accidental ACL change or bucket policy misconfiguration is applied later,
  # these settings prevent the bucket from becoming publicly accessible.
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ─── DynamoDB: appointments table ─────────────────────────────────────────────

resource "aws_dynamodb_table" "appointments" {
  name         = "${var.project}-appointments-${var.environment}"
  # PAY_PER_REQUEST eliminates the need to pre-provision read/write capacity
  # units.  At dev/demo traffic volumes there is no minimum charge, and the
  # table scales automatically if load spikes.
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
  # 14-day retention gives the team time to inspect and replay failed messages
  # without them being silently discarded by SQS's default 4-day window.
  message_retention_seconds = var.reminders_dlq_retention_seconds
  tags                      = local.common_tags
}

resource "aws_sqs_queue" "reminders" {
  name = "${var.project}-reminders-${var.environment}"

  # redrive_policy routes messages to the DLQ after maxReceiveCount failed
  # delivery attempts.  Without a DLQ, poison-pill messages (e.g., malformed
  # payloads that always crash the consumer) would loop indefinitely and block
  # every message behind them in the queue.
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.reminders_dlq.arn
    maxReceiveCount     = var.reminders_max_receive_count
  })

  tags = local.common_tags
}
