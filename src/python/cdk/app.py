"""
AWS CDK App Entry Point
Secure Data Ingestion API
"""
import aws_cdk as cdk
from data_ingestion_stack import DataIngestionStack

app = cdk.App()

# Get environment from context or default to 'dev'
environment = app.node.try_get_context("environment") or "dev"

# Stack configuration
stack_config = {
    "dev": {
        "stack_name": "DataIngestionStack-Dev",
        "description": "Development environment for secure data ingestion API",
    },
    "prod": {
        "stack_name": "DataIngestionStack-Prod",
        "description": "Production environment for secure data ingestion API",
    }
}

config = stack_config.get(environment, stack_config["dev"])

# Create the stack
DataIngestionStack(
    app,
    config["stack_name"],
    description=config["description"],
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "eu-west-2"
    ),
    deployment_env=environment,
    tags={
        "Project": "DataIngestionAPI",
        "Environment": environment,
        "ManagedBy": "CDK"
    }
)

app.synth()