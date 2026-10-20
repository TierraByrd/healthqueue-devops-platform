output "state_bucket_name" {
  description = "Name of the S3 bucket holding remote OpenTofu state."
  value       = aws_s3_bucket.tf_state.id
}

output "state_bucket_arn" {
  description = "ARN of the remote-state S3 bucket."
  value       = aws_s3_bucket.tf_state.arn
}
