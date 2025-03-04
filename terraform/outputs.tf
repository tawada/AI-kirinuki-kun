output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "public_subnets" {
  description = "IDs of the public subnets"
  value       = module.vpc.public_subnets
}

output "private_subnets" {
  description = "IDs of the private subnets"
  value       = module.vpc.private_subnets
}

output "app_repository_url" {
  description = "URL of the ECR repository for the application"
  value       = aws_ecr_repository.app_repository.repository_url
}

output "worker_repository_url" {
  description = "URL of the ECR repository for the worker"
  value       = aws_ecr_repository.worker_repository.repository_url
}

output "database_endpoint" {
  description = "Endpoint of the RDS database"
  value       = aws_db_instance.postgres.endpoint
}

output "redis_endpoint" {
  description = "Endpoint of the ElastiCache Redis cluster"
  value       = aws_elasticache_cluster.redis.cache_nodes.0.address
}

output "upload_bucket_name" {
  description = "Name of the S3 bucket for uploads"
  value       = aws_s3_bucket.upload_bucket.bucket
}

output "output_bucket_name" {
  description = "Name of the S3 bucket for outputs"
  value       = aws_s3_bucket.output_bucket.bucket
}

output "cloudfront_domain" {
  description = "Domain name of the CloudFront distribution for outputs"
  value       = aws_cloudfront_distribution.output_distribution.domain_name
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.app_lb.dns_name
}

output "app_service_name" {
  description = "Name of the ECS service for the application"
  value       = aws_ecs_service.app_service.name
}

output "worker_service_name" {
  description = "Name of the ECS service for the worker"
  value       = aws_ecs_service.worker_service.name
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.app_cluster.name
}

output "cloudwatch_dashboard_url" {
  description = "URL of the CloudWatch dashboard"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "repository_clone_url_http" {
  description = "URL to clone the repository via HTTP"
  value       = "https://git-codecommit.${var.aws_region}.amazonaws.com/v1/repos/${var.project_name}"
}

output "build_command" {
  description = "Command to build and push the Docker images"
  value       = "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.app_repository.repository_url} && docker build -t ${aws_ecr_repository.app_repository.repository_url}:latest -f docker/Dockerfile.app . && docker build -t ${aws_ecr_repository.worker_repository.repository_url}:latest -f docker/Dockerfile.worker . && docker push ${aws_ecr_repository.app_repository.repository_url}:latest && docker push ${aws_ecr_repository.worker_repository.repository_url}:latest"
}