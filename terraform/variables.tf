variable "project_name" {
  description = "Name of the project"
  default     = "ai-kirinuki"
}

variable "environment" {
  description = "Environment (development, staging, production)"
  default     = "development"
}

variable "aws_region" {
  description = "AWS region to deploy resources"
  default     = "ap-northeast-1"
}

# VPC Settings
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones to use"
  type        = list(string)
  default     = ["ap-northeast-1a", "ap-northeast-1c"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24"]
}

# Database Settings
variable "db_instance_class" {
  description = "RDS instance class"
  default     = "db.t3.small"
}

variable "db_name" {
  description = "Name of the database"
  default     = "aikirinkidb"
}

variable "db_username" {
  description = "Username for the database"
  default     = "dbadmin"
}

variable "db_password" {
  description = "Password for the database"
  sensitive   = true
}

# Redis Settings
variable "redis_node_type" {
  description = "ElastiCache node type"
  default     = "cache.t3.small"
}

# Application Settings
variable "app_cpu" {
  description = "CPU units for the application container"
  default     = "512"
}

variable "app_memory" {
  description = "Memory for the application container (in MiB)"
  default     = "1024"
}

variable "app_min_capacity" {
  description = "Minimum number of application instances"
  default     = 1
}

variable "app_max_capacity" {
  description = "Maximum number of application instances"
  default     = 5
}

# Worker Settings
variable "worker_cpu" {
  description = "CPU units for the worker container"
  default     = "1024"
}

variable "worker_memory" {
  description = "Memory for the worker container (in MiB)"
  default     = "2048"
}

variable "worker_min_capacity" {
  description = "Minimum number of worker instances"
  default     = 1
}

variable "worker_max_capacity" {
  description = "Maximum number of worker instances"
  default     = 10
}

# Other Settings
variable "flask_secret_key" {
  description = "Secret key for Flask application"
  sensitive   = true
  default     = "change_this_in_production"
}