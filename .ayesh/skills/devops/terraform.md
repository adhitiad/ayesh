---
name: terraform
description: "Infrastructure as Code (IaC) dengan Terraform. Trigger: /terraform"
---

# Terraform Infrastructure as Code

## Basic Commands
```bash
terraform init
terraform plan
terraform apply
terraform apply -auto-approve
terraform destroy

terraform fmt
terraform validate
terraform output
terraform show
terraform state list
terraform state show aws_instance.example
```

## Provider
```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
  default_tags {
    tags = {
      Environment = "production"
    }
  }
}
```

## Resources
```hcl
resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"
  
  tags = {
    Name = "web-server"
  }
}

resource "aws_s3_bucket" "data" {
  bucket = "my-data-bucket"
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}
```

## Variables
```hcl
variable "region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region"
}

variable "instance_count" {
  type    = number
  default = 1
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Must be dev, staging, or prod"
  }
}
```

## Output
```hcl
output "instance_ip" {
  value = aws_instance.web.public_ip
}

output "bucket_arn" {
  value = aws_s3_bucket.data.arn
}
```

## State Management
```bash
terraform state pull
terraform state push state.tfstate
terraform state mv aws_instance.old aws_instance.new
terraform state rm aws_instance.example
terraform import aws_instance.example i-1234567890
```

```hcl
terraform {
  backend "s3" {
    bucket         = "my-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

## Modules
```hcl
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"

  name = "my-vpc"
  cidr = "10.0.0.0/16"
  
  azs             = ["us-east-1a", "us-east-1b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]
}
```

## Data Sources
```hcl
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]
  
  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

data "aws_caller_identity" "current" {}

output "account_id" {
  value = data.aws_caller_identity.current.account_id
}
```

## Workspaces
```bash
terraform workspace list
terraform workspace new dev
terraform workspace select dev
terraform workspace show
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Init error | Cek provider version, backend |
| Plan error | `terraform validate`, cek syntax |
| Apply error | Cek resource limits, permissions |
| State lock | `terraform force-unlock LOCK_ID` |
| Drift detected | `terraform plan`, re-apply |
