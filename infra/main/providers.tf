terraform {
  required_version = ">= 1.13"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
  # "test"/"test" are LocalStack's well-known placeholder credentials — not
  # real AWS keys.  LocalStack ignores credential values; the skip_* flags
  # below prevent the provider from attempting real-AWS validation.
  access_key = "test"
  secret_key = "test"

  endpoints {
    s3       = "http://localhost:4566"
    dynamodb = "http://localhost:4566"
    sqs      = "http://localhost:4566"
  }

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true
}
