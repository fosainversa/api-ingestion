# Secure Data Ingestion API - AWS CDK Solution

A production-ready, secure data ingestion API built with AWS CDK using only free-tier resources.

## 🏗️ Architecture

```
Internet → API Gateway (with security layers) → Lambda → DynamoDB
                ↓
          CloudWatch Logs
                ↓
          EventBridge (weekly) → Lambda → S3 (summary)
```

## 🔒 Security Features

- **JWT-based Lambda Authorizer** - Token validation with RS256
- **API Keys & Usage Plans** - Rate limiting and identification
- **Request Validation** - JSON schema validation
- **IP Whitelisting** - Resource policy (optional)
- **CloudWatch Logging** - Full audit trail
- **IAM Least Privilege** - Minimal permissions
- **KMS Encryption** - Environment variables encrypted
- **HTTPS Only** - TLS 1.2+ enforced

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
# Enter your AWS Access Key ID, Secret Access Key, and set region to eu-west-2

# Bootstrap CDK (first time only)
cdk bootstrap aws://ACCOUNT-ID/AWS_Region
```

### 3. Generate JWT Keys

```bash
# REQUIRED before deployment!
cd lambda
python generate_jwt.py
cd ..
```

### 4. Deploy

```bash
# Synthesize CloudFormation template
cdk synth

# Deploy the stack
cdk deploy

# Save outputs
cdk deploy --outputs-file outputs.json
```

### 5. Test the API

```bash

bash test_api.sh
```

## 📁 Project Structure

```
aws-data-ingestion-api/
├── README.md
├── SETUP_GUIDE.md        ← Detailed 20-step guide
├── app.py                ← CDK entry point
├── cdk.json              ← CDK configuration
├── requirements.txt      ← Python dependencies
│
├── stacks/
│   └── data_ingestion_stack.py
│
├── lambda/
│   ├── authorizer.py
│   ├── ingest_handler.py
│   ├── weekly_summary_handler.py
│   └── generate_keys.py
│
├── scripts/
│   └── generate_test_token.py
│
└── tests/
    ├── test_authorizer.py
    ├── test_ingest_handler.py
    └── test_weekly_summary.py
```

## 💰 Cost Estimate (Free Tier)

| Service | Free Tier | Expected Usage | Cost |
|---------|-----------|----------------|------|
| API Gateway | 1M requests/month | <100K | $0 |
| Lambda | 1M requests, 400K GB-sec | <50K invocations | $0 |
| DynamoDB | 25 GB, 25 WCU/RCU | <1 GB | $0 |
| S3 | 5 GB storage | <1 MB | $0 |
| CloudWatch Logs | 5 GB ingestion | <2 GB | $0 |
| **Total** | | | **$0/month** |

## 🧪 Testing

```bash
# Run unit tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=lambda --cov-report=html
```

## 🗑️ Cleanup

```bash
# Destroy all resources
cdk destroy
```

## 📚 Documentation

- **SETUP_GUIDE.md** - Complete 20-step deployment guide
- **ARCHITECTURE.md** - Technical architecture details
- **DEPLOYMENT.md** - Advanced deployment scenarios

## 🔐 Security Notes

⚠️ **NEVER commit `private_key.pem` to version control** - it's already in `.gitignore`

## 📄 License

MIT License

---

**Built with ❤️ using AWS CDK and Python**
