terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Bucket is passed at init time, so the account ID isn't in the code:
  # terraform init -backend-config="bucket=dsl-tfstate-<account id>"
  backend "s3" {
    key          = "dev/terraform.tfstate"
    region       = "ap-southeast-2"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = "ap-southeast-2"

  default_tags {
    tags = {
      project     = "backblaze-drive-stats"
      managed_by  = "terraform"
      environment = "dev"
    }
  }
}
