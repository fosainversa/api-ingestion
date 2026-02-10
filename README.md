# Secure Data Ingestion API - AWS CDK Solution

A secure data ingestion API built with AWS CDK using only free-tier resources.

## 🏗️ Architecture

<img width="1721" height="1222" alt="image" src="https://github.com/user-attachments/assets/b411dfbd-dd37-4c82-8507-8305def38c7f" />


```
Client → API Gateway → Authorizer Lambda → SSM → Authorizer Lambda 
→ API Gateway → Ingest Lambda → DynamoDB → (weekly) Summary Lambda → S3
```

## 📁 Project Structure

```
secure_free_tier_api/
├── app.py                        # CDK entry point
├── requirements.txt              # CDK dependencies
├── src/python/
│   ├── cdk/
│   │   └── data_ingestion_stack.py
│   └── lambda/
│       ├── authorizer.py
│       ├── ingest_handler.py
│       ├── weekly_summary_handler.py
│       └── requirements.txt      # PyJWT only
│
└── test_api.sh                   # Testing script

```

## 🔒 Security Features

### **Authentication & Authorization**

- **JWT Bearer Token** - HS256 algorithm with SSM-stored secrets
- **API Keys** - Rate limiting and client identification
- **Request Validation** - JSON schema validation at API Gateway

### **AWS Security**
- **IAM Least Privilege** - Minimal permissions per function
- **AWS-Managed Encryption** - DynamoDB and S3 encryption at rest
- **SSM Parameter Store** - Encrypted secret storage (FREE)
- **CloudWatch Logging** - Full audit trail with retention
- **HTTPS Only** - API Gateway enforces HTTPS (default)

## 📋 Prerequisites

- AWS Account (new account recommended for free tier)
- AWS CLI configured
- Node.js 18+ and npm
- Python 3.12+
- Git

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
npm install -g aws-cdk
```

### 2. Configure AWS

```bash
# Configure AWS CLI
aws configure
# Enter your AWS Access Key ID, Secret Access Key and Region 

# Bootstrap CDK (first time only)
cdk bootstrap aws://ACCOUNT-ID/AWS_Region
```

### 3. Deploy

```bash
# Synthesize CloudFormation template
cdk synth

# Deploy the stack
cdk deploy

# Save outputs if needed
cdk deploy --outputs-file outputs.json 
```

### 4. Test the API

```bash 
chmod +x test_api.sh
./test_api.sh
```
<img width="1017" height="554" alt="image" src="https://github.com/user-attachments/assets/34d55232-4add-43a8-815b-6b612bb38645" />


## 💰 Cost Estimate (Free Tier)

| Service | Free Tier | Expected Usage | Cost |
|---------|-----------|----------------|------|
| API Gateway | 1M requests/month | <100K | $0 |
| Lambda | 1M requests, 400K GB-sec | <50K invocations | $0 |
| DynamoDB | 25 GB, 25 WCU/RCU | <1 GB | $0 |
| S3 | 5 GB storage | <1 MB | $0 |
| CloudWatch Logs | 5 GB ingestion | <2 GB | $0 |
| **Total** | | | **$0/month** |


## 🗑️ Cleanup

```bash
# Destroy all resources
cdk destroy
```

