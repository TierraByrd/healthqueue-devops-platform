locals {
  common_tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "opentofu"
  }
}

resource "aws_s3_bucket" "tf_state" {
  bucket = "healthqueue-tofu-state"

  tags = local.common_tags
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  versioning_configuration {
    # Versioning on the state bucket allows rolling back to a previous state
    # file if a bad `tofu apply` corrupts it.  Without versioning, an
    # interrupted apply could leave state permanently unrecoverable.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      # State files can contain sensitive values (e.g., connection strings,
      # secret outputs).  Encrypting at rest ensures those values are not
      # readable if the underlying storage is accessed directly.
      sse_algorithm = "AES256"
    }
  }
}
