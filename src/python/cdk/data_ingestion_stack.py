"""
Main CDK Stack for Secure Data Ingestion API - 100% FREE TIER VERSION
Implements enterprise-grade security with free-tier AWS resources
"""
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_apigateway as apigateway,
    aws_s3 as s3,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
    aws_iam as iam,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_ssm as ssm,
)
from constructs import Construct
import os
import secrets
import string


class DataIngestionStack(Stack):
    """
    Secure Data Ingestion Stack with:
    - API Gateway with JWT authorizer
    - Lambda functions for data processing
    - DynamoDB for data persistence
    - S3 for weekly summaries
    - CloudWatch for monitoring
    - SSM Parameter Store for JWT secrets (FREE!)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        deployment_env: str = "dev",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Environment-specific configuration
        self.deployment_env = deployment_env
        is_production = deployment_env == "prod"

        # ========================================
        # JWT Secret in SSM Parameter Store (FREE!)
        # ========================================
        def generate_jwt_secret():
            """Generate a secure random secret (64 characters)"""
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"
            return ''.join(secrets.choice(alphabet) for _ in range(64))

        jwt_secret_param = ssm.StringParameter(
            self,
            "JWTSecretParam",
            description=f"JWT signing secret for {deployment_env}",
            string_value=generate_jwt_secret(),
            tier=ssm.ParameterTier.STANDARD,  # FREE tier
        )

        # ========================================
        # DynamoDB Table
        # ========================================
        table = dynamodb.Table(
            self,
            "DataTable",
            partition_key=dynamodb.Attribute(
                name="id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=is_production,
            removal_policy=RemovalPolicy.DESTROY if not is_production else RemovalPolicy.RETAIN,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES if is_production else None,
        )

        # Add GSI for querying by userId
        table.add_global_secondary_index(
            index_name="UserIdIndex",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", type=dynamodb.AttributeType.NUMBER
            ),
        )

        # ========================================
        # S3 Bucket for Weekly Summaries
        # ========================================
        summary_bucket = s3.Bucket(
            self,
            "SummaryBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=is_production,
            lifecycle_rules=[
                s3.LifecycleRule(
                    enabled=True,
                    expiration=Duration.days(90),  # Auto-delete after 90 days
                )
            ],
            removal_policy=RemovalPolicy.DESTROY if not is_production else RemovalPolicy.RETAIN,
            auto_delete_objects=True if not is_production else False,
        )

        # ========================================
        # Lambda: JWT Authorizer
        # ========================================
        authorizer_lambda = lambda_.Function(
            self,
            "AuthorizerFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="authorizer.handler",
            code=lambda_.Code.from_asset("src/python/lambda"),
            timeout=Duration.seconds(10),
            memory_size=256,
            environment={
                "LOG_LEVEL": "INFO" if is_production else "DEBUG",
                "JWT_SECRET_PARAM": jwt_secret_param.parameter_name,
            },
            # No environment_encryption - uses AWS-managed encryption (FREE!)
            description="JWT token authorizer for API Gateway",
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Grant permission to read SSM parameter
        jwt_secret_param.grant_read(authorizer_lambda)

        # ========================================
        # Lambda: Data Ingestion Handler
        # ========================================
        ingest_lambda = lambda_.Function(
            self,
            "IngestFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="ingest_handler.handler",
            code=lambda_.Code.from_asset("src/python/lambda"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "TABLE_NAME": table.table_name,
                "LOG_LEVEL": "INFO" if is_production else "DEBUG",
                "ENVIRONMENT": deployment_env,
            },
            # No environment_encryption - uses AWS-managed encryption (FREE!)
            description="Ingests JSON data into DynamoDB",
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Grant DynamoDB write permissions
        table.grant_write_data(ingest_lambda)

        # ========================================
        # Lambda: Weekly Summary Generator
        # ========================================
        summary_lambda = lambda_.Function(
            self,
            "SummaryFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="weekly_summary_handler.handler",
            code=lambda_.Code.from_asset("src/python/lambda"),
            timeout=Duration.seconds(60),
            memory_size=512,  # More memory for scanning
            environment={
                "TABLE_NAME": table.table_name,
                "BUCKET_NAME": summary_bucket.bucket_name,
                "LOG_LEVEL": "INFO" if is_production else "DEBUG",
            },
            # No environment_encryption - uses AWS-managed encryption (FREE!)
            description="Generates weekly summary reports",
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        # Grant permissions
        table.grant_read_data(summary_lambda)
        summary_bucket.grant_put(summary_lambda)

        # ========================================
        # EventBridge Rule: Weekly Summary
        # ========================================
        summary_rule = events.Rule(
            self,
            "WeeklySummaryRule",
            description="Trigger weekly summary generation every Monday at 9 AM UTC",
            schedule=events.Schedule.cron(
                minute="0",
                hour="9",
                week_day="MON",
            ),
            enabled=True,
        )
        summary_rule.add_target(targets.LambdaFunction(summary_lambda))

        # ========================================
        # API Gateway: REST API
        # ========================================
        
        # CloudWatch Log Group for API Gateway
        api_log_group = logs.LogGroup(
            self,
            "ApiLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Create API Gateway
        api = apigateway.RestApi(
            self,
            "DataIngestionApi",
            rest_api_name=f"DataIngestionAPI-{deployment_env}",
            description=f"Secure data ingestion API ({deployment_env})",
            cloud_watch_role=True,
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                metrics_enabled=True,
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=not is_production,  # Disable in prod (contains request/response)
                tracing_enabled=True,  # Enable X-Ray
                throttling_rate_limit=10,  # 10 requests per second
                throttling_burst_limit=20,  # Burst capacity
                access_log_destination=apigateway.LogGroupLogDestination(api_log_group),
                access_log_format=apigateway.AccessLogFormat.json_with_standard_fields(
                    caller=True,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True,
                ),
            ),
            endpoint_types=[apigateway.EndpointType.REGIONAL],
        )

        # ========================================
        # API Gateway: JWT Authorizer
        # ========================================
        authorizer = apigateway.TokenAuthorizer(
            self,
            "JWTAuthorizer",
            handler=authorizer_lambda,
            identity_source="method.request.header.Authorization",
            results_cache_ttl=Duration.minutes(5),  # Cache auth decisions
            authorizer_name="JWTAuthorizer",
        )

        # ========================================
        # API Gateway: Request Validation
        # ========================================
        
        # Request model for validation
        request_model = api.add_model(
            "DataIngestionModel",
            content_type="application/json",
            model_name="DataIngestionModel",
            schema=apigateway.JsonSchema(
                schema=apigateway.JsonSchemaVersion.DRAFT4,
                title="DataIngestionRequest",
                type=apigateway.JsonSchemaType.OBJECT,
                properties={
                    "userId": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING,
                        min_length=1,
                        max_length=100,
                        pattern="^[a-zA-Z0-9_-]+$",  # Alphanumeric, underscore, hyphen
                        description="User identifier",
                    ),
                    "eventType": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING,
                        min_length=1,
                        max_length=50,
                        description="Type of event",
                    ),
                    "data": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.OBJECT,
                        description="Custom data payload",
                    ),
                },
                required=["userId", "data"],
            ),
        )

        # Request validator
        validator = api.add_request_validator(
            "RequestValidator",
            validate_request_body=True,
            validate_request_parameters=True,
        )

        # ========================================
        # API Gateway: Usage Plan & API Key
        # ========================================
        
        # Create API Key
        api_key = api.add_api_key(
            "ApiKey",
            api_key_name=f"DataIngestionKey-{deployment_env}",
            description=f"API key for data ingestion ({deployment_env})",
        )

        # Create Usage Plan with rate limiting
        usage_plan = api.add_usage_plan(
            "UsagePlan",
            name=f"Standard-{deployment_env}",
            description="Standard usage plan with rate limiting",
            throttle=apigateway.ThrottleSettings(
                rate_limit=10,  # 10 requests per second
                burst_limit=20,  # 20 burst capacity
            ),
            quota=apigateway.QuotaSettings(
                limit=100000,  # 100K requests per month (well within free tier)
                period=apigateway.Period.MONTH,
            ),
        )

        # Associate API key with usage plan
        usage_plan.add_api_key(api_key)

        # ========================================
        # API Gateway: Resources and Methods
        # ========================================
        
        # Health check endpoint (no auth required)
        health_resource = api.root.add_resource("health")
        health_resource.add_method(
            "GET",
            apigateway.MockIntegration(
                integration_responses=[
                    apigateway.IntegrationResponse(
                        status_code="200",
                        response_templates={
                            "application/json": '{"status": "healthy", "timestamp": "$context.requestTime"}'
                        },
                    )
                ],
                request_templates={"application/json": '{"statusCode": 200}'},
            ),
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_models={"application/json": apigateway.Model.EMPTY_MODEL},
                )
            ],
        )

        # Data ingestion endpoint (requires JWT auth + API key)
        data_resource = api.root.add_resource("data")
        data_method = data_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(
                ingest_lambda,
                proxy=True,
                integration_responses=[
                    apigateway.IntegrationResponse(status_code="200"),
                    apigateway.IntegrationResponse(status_code="400"),
                    apigateway.IntegrationResponse(status_code="500"),
                ],
            ),
            authorizer=authorizer,
            api_key_required=True,
            request_models={"application/json": request_model},
            request_validator=validator,
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_models={"application/json": apigateway.Model.EMPTY_MODEL},
                ),
                apigateway.MethodResponse(status_code="400"),
                apigateway.MethodResponse(status_code="401"),
                apigateway.MethodResponse(status_code="403"),
                apigateway.MethodResponse(status_code="429"),
                apigateway.MethodResponse(status_code="500"),
            ],
        )

        # Associate usage plan with API stage
        usage_plan.add_api_stage(
            stage=api.deployment_stage,
            throttle=[
                apigateway.ThrottlingPerMethod(
                    method=data_method,
                    throttle=apigateway.ThrottleSettings(
                        rate_limit=10,
                        burst_limit=20,
                    ),
                )
            ],
        )

        # ========================================
        # CloudWatch Alarms
        # ========================================
        
        # Alarm for high 4XX error rate
        alarm_4xx = cloudwatch.Alarm(
            self,
            "High4XXErrors",
            metric=api.metric_client_error(),
            threshold=10,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            alarm_description="API Gateway 4XX errors exceed threshold",
            alarm_name=f"DataIngestionAPI-4XX-{deployment_env}",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Alarm for high 5XX error rate
        alarm_5xx = cloudwatch.Alarm(
            self,
            "High5XXErrors",
            metric=api.metric_server_error(),
            threshold=5,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            alarm_description="API Gateway 5XX errors exceed threshold",
            alarm_name=f"DataIngestionAPI-5XX-{deployment_env}",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Alarm for Lambda errors
        alarm_lambda = cloudwatch.Alarm(
            self,
            "LambdaErrors",
            metric=ingest_lambda.metric_errors(),
            threshold=3,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            alarm_description="Lambda function errors exceed threshold",
            alarm_name=f"DataIngestionLambda-Errors-{deployment_env}",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # ========================================
        # Outputs
        # ========================================
        
        CfnOutput(
            self,
            "ApiEndpoint",
            value=api.url,
            description="API Gateway endpoint URL",
            export_name=f"DataIngestionAPI-Endpoint-{deployment_env}",
        )

        CfnOutput(
            self,
            "ApiKeyId",
            value=api_key.key_id,
            description="API Key ID (retrieve value from AWS Console)",
            export_name=f"DataIngestionAPI-KeyId-{deployment_env}",
        )

        CfnOutput(
            self,
            "TableName",
            value=table.table_name,
            description="DynamoDB table name",
            export_name=f"DataIngestionAPI-TableName-{deployment_env}",
        )

        CfnOutput(
            self,
            "BucketName",
            value=summary_bucket.bucket_name,
            description="S3 bucket for weekly summaries",
            export_name=f"DataIngestionAPI-BucketName-{deployment_env}",
        )

        CfnOutput(
            self,
            "HealthCheckUrl",
            value=f"{api.url}health",
            description="Health check endpoint (no auth required)",
            export_name=f"DataIngestionAPI-HealthCheck-{deployment_env}",
        )

        CfnOutput(
            self,
            "DataIngestionUrl",
            value=f"{api.url}data",
            description="Data ingestion endpoint (requires JWT + API key)",
            export_name=f"DataIngestionAPI-DataUrl-{deployment_env}",
        )

        CfnOutput(
            self,
            "JWTSecretParamOutput",
            value=jwt_secret_param.parameter_name,
            description="SSM Parameter name for JWT secret",
            export_name=f"DataIngestionAPI-JWTSecretParam-{deployment_env}",
        )