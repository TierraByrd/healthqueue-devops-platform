terraform {
  backend "s3" {
    bucket = "healthqueue-tofu-state"
    key    = "healthqueue/main/terraform.tfstate"
    region = "us-east-1"

    # LocalStack endpoint and path-style URLs (required for non-AWS S3).
    endpoints = {
      s3 = "http://localhost:4566"
    }
    force_path_style = true

    # LocalStack test credentials; skip all real-AWS validation checks.
    access_key                  = "test"
    secret_key                  = "test"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true

    # Native S3 state locking — added in OpenTofu 1.8 and recommended over
    # DynamoDB locking in OpenTofu 1.13+.  Creates a <key>.tflock object using
    # an S3 conditional write (If-None-Match: *) so no separate DynamoDB table
    # is required.
    use_lockfile = true
  }
}
