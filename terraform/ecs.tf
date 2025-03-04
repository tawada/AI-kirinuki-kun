# ECS Task Definition for the application
resource "aws_ecs_task_definition" "app_task" {
  family                   = "${var.project_name}-app-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.app_cpu
  memory                   = var.app_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-app"
      image     = "${aws_ecr_repository.app_repository.repository_url}:latest"
      essential = true
      
      portMappings = [
        {
          containerPort = 5000
          hostPort      = 5000
          protocol      = "tcp"
        }
      ]
      
      environment = [
        {
          name  = "FLASK_APP"
          value = "run.py"
        },
        {
          name  = "FLASK_ENV"
          value = var.environment
        },
        {
          name  = "USE_S3"
          value = "true"
        },
        {
          name  = "S3_UPLOAD_BUCKET"
          value = aws_s3_bucket.upload_bucket.bucket
        },
        {
          name  = "S3_OUTPUT_BUCKET"
          value = aws_s3_bucket.output_bucket.bucket
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "CLOUDFRONT_DOMAIN"
          value = aws_cloudfront_distribution.output_distribution.domain_name
        },
        {
          name  = "DATABASE_URL"
          value = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.endpoint}/${var.db_name}"
        },
        {
          name  = "CELERY_BROKER_URL"
          value = "redis://${aws_elasticache_cluster.redis.cache_nodes.0.address}:6379/0"
        },
        {
          name  = "CELERY_RESULT_BACKEND"
          value = "redis://${aws_elasticache_cluster.redis.cache_nodes.0.address}:6379/0"
        },
        {
          name  = "MAX_VIDEO_LENGTH"
          value = "3600"
        },
        {
          name  = "HIGHLIGHT_PERCENTAGE"
          value = "30"
        }
      ]
      
      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = aws_ssm_parameter.secret_key.arn
        }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app_log_group.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "app"
        }
      }
    }
  ])

  tags = {
    Name        = "${var.project_name}-app-task"
    Environment = var.environment
  }
}

# ECS Task Definition for the worker
resource "aws_ecs_task_definition" "worker_task" {
  family                   = "${var.project_name}-worker-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-worker"
      image     = "${aws_ecr_repository.worker_repository.repository_url}:latest"
      essential = true
      
      environment = [
        {
          name  = "FLASK_APP"
          value = "run.py"
        },
        {
          name  = "FLASK_ENV"
          value = var.environment
        },
        {
          name  = "USE_S3"
          value = "true"
        },
        {
          name  = "S3_UPLOAD_BUCKET"
          value = aws_s3_bucket.upload_bucket.bucket
        },
        {
          name  = "S3_OUTPUT_BUCKET"
          value = aws_s3_bucket.output_bucket.bucket
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "DATABASE_URL"
          value = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.endpoint}/${var.db_name}"
        },
        {
          name  = "CELERY_BROKER_URL"
          value = "redis://${aws_elasticache_cluster.redis.cache_nodes.0.address}:6379/0"
        },
        {
          name  = "CELERY_RESULT_BACKEND"
          value = "redis://${aws_elasticache_cluster.redis.cache_nodes.0.address}:6379/0"
        },
        {
          name  = "MAX_VIDEO_LENGTH"
          value = "3600"
        },
        {
          name  = "HIGHLIGHT_PERCENTAGE"
          value = "30"
        },
        {
          name  = "C_FORCE_ROOT"
          value = "true"
        }
      ]
      
      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = aws_ssm_parameter.secret_key.arn
        }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker_log_group.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])

  tags = {
    Name        = "${var.project_name}-worker-task"
    Environment = var.environment
  }
}

# ECS Service for the application
resource "aws_ecs_service" "app_service" {
  name                              = "${var.project_name}-app-service-${var.environment}"
  cluster                           = aws_ecs_cluster.app_cluster.id
  task_definition                   = aws_ecs_task_definition.app_task.arn
  desired_count                     = var.app_min_capacity
  launch_type                       = "FARGATE"
  platform_version                  = "LATEST"
  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.app_sg.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app_tg.arn
    container_name   = "${var.project_name}-app"
    container_port   = 5000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = {
    Name        = "${var.project_name}-app-service"
    Environment = var.environment
  }
  
  lifecycle {
    ignore_changes = [desired_count]
  }
  
  depends_on = [
    aws_lb_listener.http,
    aws_db_instance.postgres,
    aws_elasticache_cluster.redis
  ]
}

# ECS Service for the worker
resource "aws_ecs_service" "worker_service" {
  name                       = "${var.project_name}-worker-service-${var.environment}"
  cluster                    = aws_ecs_cluster.app_cluster.id
  task_definition            = aws_ecs_task_definition.worker_task.arn
  desired_count              = var.worker_min_capacity
  launch_type                = "FARGATE"
  platform_version           = "LATEST"
  scheduling_strategy        = "REPLICA"
  
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 100
    base              = 1
  }

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.app_sg.id]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = {
    Name        = "${var.project_name}-worker-service"
    Environment = var.environment
  }
  
  lifecycle {
    ignore_changes = [desired_count]
  }
  
  depends_on = [
    aws_db_instance.postgres,
    aws_elasticache_cluster.redis
  ]
}

# Auto Scaling Configuration for Application
resource "aws_appautoscaling_target" "app_target" {
  max_capacity       = var.app_max_capacity
  min_capacity       = var.app_min_capacity
  resource_id        = "service/${aws_ecs_cluster.app_cluster.name}/${aws_ecs_service.app_service.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "app_policy" {
  name               = "${var.project_name}-app-autoscaling-policy"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.app_target.resource_id
  scalable_dimension = aws_appautoscaling_target.app_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.app_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Auto Scaling Configuration for Worker
resource "aws_appautoscaling_target" "worker_target" {
  max_capacity       = var.worker_max_capacity
  min_capacity       = var.worker_min_capacity
  resource_id        = "service/${aws_ecs_cluster.app_cluster.name}/${aws_ecs_service.worker_service.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "worker_policy" {
  name               = "${var.project_name}-worker-autoscaling-policy"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.worker_target.resource_id
  scalable_dimension = aws_appautoscaling_target.worker_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.worker_target.service_namespace

  target_tracking_scaling_policy_configuration {
    customized_metric_specification {
      metric_name = "CeleryQueueLength"
      namespace   = "CustomMetrics/Celery"
      statistic   = "Average"
      unit        = "Count"
    }
    
    target_value       = 10.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "app_log_group" {
  name              = "/ecs/${var.project_name}-app-${var.environment}"
  retention_in_days = 14
  
  tags = {
    Name        = "${var.project_name}-app-logs"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "worker_log_group" {
  name              = "/ecs/${var.project_name}-worker-${var.environment}"
  retention_in_days = 14
  
  tags = {
    Name        = "${var.project_name}-worker-logs"
    Environment = var.environment
  }
}

# SSM Parameters
resource "aws_ssm_parameter" "secret_key" {
  name  = "/${var.project_name}/${var.environment}/SECRET_KEY"
  type  = "SecureString"
  value = var.flask_secret_key
  
  tags = {
    Name        = "${var.project_name}-secret-key"
    Environment = var.environment
  }
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-dashboard-${var.environment}"
  
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ServiceName", aws_ecs_service.app_service.name, "ClusterName", aws_ecs_cluster.app_cluster.name]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "ECS App CPU Utilization"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ServiceName", aws_ecs_service.worker_service.name, "ClusterName", aws_ecs_cluster.app_cluster.name]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "ECS Worker CPU Utilization"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ECS", "MemoryUtilization", "ServiceName", aws_ecs_service.app_service.name, "ClusterName", aws_ecs_cluster.app_cluster.name]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "ECS App Memory Utilization"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ECS", "MemoryUtilization", "ServiceName", aws_ecs_service.worker_service.name, "ClusterName", aws_ecs_cluster.app_cluster.name]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "ECS Worker Memory Utilization"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.app_lb.arn_suffix]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "ALB Request Count"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ElastiCache", "CPUUtilization", "CacheClusterId", aws_elasticache_cluster.redis.id]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "ElastiCache CPU Utilization"
        }
      }
    ]
  })
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "app_cpu_high" {
  alarm_name          = "${var.project_name}-app-cpu-high-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = "60"
  statistic           = "Average"
  threshold           = "85"
  alarm_description   = "This metric monitors app service cpu utilization"
  
  dimensions = {
    ClusterName = aws_ecs_cluster.app_cluster.name
    ServiceName = aws_ecs_service.app_service.name
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "worker_cpu_high" {
  alarm_name          = "${var.project_name}-worker-cpu-high-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = "60"
  statistic           = "Average"
  threshold           = "85"
  alarm_description   = "This metric monitors worker service cpu utilization"
  
  dimensions = {
    ClusterName = aws_ecs_cluster.app_cluster.name
    ServiceName = aws_ecs_service.worker_service.name
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# SNS Topic for Alarms
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts-${var.environment}"
  
  tags = {
    Name        = "${var.project_name}-alerts"
    Environment = var.environment
  }
}