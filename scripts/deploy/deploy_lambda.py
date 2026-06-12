import boto3
import json
import os
import sys
import time
import zipfile
import tempfile
import argparse
import shutil
import logging
from subprocess import run as Run
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

iam_client = None
lambda_client = None

def create_iam_role(role_name, trust_policy, policy_document):
  try:
      # Create role
      response = iam_client.create_role(
          RoleName=role_name,
          AssumeRolePolicyDocument=json.dumps(trust_policy)
      )
      role_arn = response['Role']['Arn']
      
      # Attach inline policy
      iam_client.put_role_policy(
          RoleName=role_name,
          PolicyName=f"{role_name}-policy",
          PolicyDocument=json.dumps(policy_document)
      )
      logger.info(f"Created new IAM role: {role_arn}")
      
      # Wait for role to be available
      time.sleep(10)
      
      return role_arn
      
  except iam_client.exceptions.EntityAlreadyExistsException:
      response = iam_client.get_role(RoleName=role_name)
      logger.info(f"IAM role {role_name} already exists, using existing role: {response['Role']['Arn']}")

      # Attach inline policy
      iam_client.put_role_policy(
          RoleName=role_name,
          PolicyName=f"{role_name}-policy",
          PolicyDocument=json.dumps(policy_document)
      )
      
      # Wait for role to be available
      time.sleep(10)

      return response['Role']['Arn']

def create_or_update_lambda_function(function_name, role_arn, handler, files, dependencies, env, region, s3_bucket=None, layers=None):
  try:
    # Create deployment package
    with tempfile.TemporaryDirectory() as temp_dir:
      # Copy source files
      for target_name, source_path in files.items():
        with open(source_path, 'r') as src:
          file_path = Path(f"{temp_dir}/{target_name}")
          file_path.parent.mkdir(parents=True, exist_ok=True)
          with open(f"{temp_dir}/{target_name}", 'w') as dst:
            dst.write(src.read())
        logger.info(f"Added file to package: {target_name}")
      
      # Install dependencies if any
      if dependencies:
        logger.info(f"Installing dependencies: {', '.join(dependencies)}")
        for dep in dependencies:
          Run(['uv', 'pip', 'install', dep, '--target', temp_dir,
               '--python-platform', 'linux', '--python-version', '3.13', '--quiet'], check=True)
        
      # Create ZIP file
      zip_path = f"{temp_dir}_deployment.zip"
      with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files_in_dir in os.walk(temp_dir):
          for file in files_in_dir:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, temp_dir)
            zipf.write(file_path, arcname)
      
      with open(zip_path, 'rb') as f:
        zip_content = f.read()
      
      with open('package.zip', 'wb') as z:
        z.write(zip_content)
      
      zip_size_mb = len(zip_content) / (1024 * 1024)
      logger.info(f"Created deployment package: {zip_size_mb:.1f} MB")
      os.remove(zip_path)
      
      # Use S3 if package > 50MB or bucket specified
      use_s3 = zip_size_mb > 50 or s3_bucket
      code_config = None
      
      if use_s3:
        if not s3_bucket:
          # Create temp bucket
          account_id = boto3.client('sts').get_caller_identity()['Account']
          s3_bucket = f"lambda-deploy-{account_id}-{region}"
          s3_client = boto3.client('s3', region_name=region)
          try:
            if region == 'us-east-1':
              s3_client.create_bucket(Bucket=s3_bucket)
            else:
              s3_client.create_bucket(Bucket=s3_bucket, CreateBucketConfiguration={'LocationConstraint': region})
            logger.info(f"Created S3 bucket: {s3_bucket}")
          except s3_client.exceptions.BucketAlreadyOwnedByYou:
            pass
          except s3_client.exceptions.BucketAlreadyExists:
            pass
        
        s3_key = f"lambda/{function_name}.zip"
        s3_client = boto3.client('s3', region_name=region)
        s3_client.put_object(Bucket=s3_bucket, Key=s3_key, Body=zip_content)
        logger.info(f"Uploaded to s3://{s3_bucket}/{s3_key}")
        code_config = {'S3Bucket': s3_bucket, 'S3Key': s3_key}
      else:
        code_config = {'ZipFile': zip_content}
      
      # Check if function exists
      function_exists = False
      try:
        lambda_client.get_function(FunctionName=function_name)
        function_exists = True
      except lambda_client.exceptions.ResourceNotFoundException:
        pass
      
      # NOTE: 'Runtime' is the AWS Lambda managed-runtime identifier, NOT the
      # EC2 box's interpreter. It is pinned to a Lambda-SUPPORTED version and
      # is independent of the python3.14/3.13 choice the bootstrap makes for
      # the code-editor host. Do not bump this to 3.14 until AWS Lambda
      # publishes a python3.14 runtime (CreateFunction rejects unsupported
      # runtimes). python3.13 is the latest Lambda-supported line as of now.
      config_params = {
        'FunctionName': function_name, 'Runtime': 'python3.13', 'Role': role_arn, 'Handler': handler,
        'Description': f'MCP server: {function_name}', 'Timeout': 300, 'MemorySize': 512,
        'Environment': {'Variables': env}
      }
      if layers:
        config_params['Layers'] = layers
        logger.info(f"Attaching {len(layers)} layer(s)")
      
      if function_exists:
        logger.info(f"Function {function_name} exists, updating...")
        if use_s3:
          lambda_client.update_function_code(FunctionName=function_name, S3Bucket=s3_bucket, S3Key=s3_key)
        else:
          lambda_client.update_function_code(FunctionName=function_name, ZipFile=zip_content)
        
        waiter = lambda_client.get_waiter('function_updated')
        waiter.wait(FunctionName=function_name)
        
        response = lambda_client.update_function_configuration(**config_params)
        function_arn = response['FunctionArn']
        logger.info(f"Updated lambda function: {function_arn}")
      else:
        config_params['Code'] = code_config
        response = lambda_client.create_function(**config_params)
        function_arn = response['FunctionArn']
        logger.info(f"Created lambda function: {function_arn}")

      return function_arn
      
  except Exception as e:
    logger.error(f"Failed to create/update Lambda function {function_name}: {str(e)}")
    raise


def main():
  global iam_client, lambda_client

  parser = argparse.ArgumentParser(description="Deploy Lambda function to AWS")
  parser.add_argument('--region', help="AWS Region to use.", default=os.getenv("AWS_REGION", "us-east-1"))
  parser.add_argument('--server-name', default='pellier-mcp-server', help='The name of the server deployed by this function.')
  parser.add_argument('--db-cluster-arn', help="Aurora PostgreSQL DB cluster ARN")
  parser.add_argument('--secret-arn', help="AWS Secrets Manager secret ARN")
  parser.add_argument('--database', help="The name of the database to connect to", default="postgres")
  parser.add_argument('--mcp-server-path', default='./', help='Path to the MCP server entrypoint file.')
  parser.add_argument('--handler', default='pellier_search_server.lambda_handler', help='Lambda handler function')
  parser.add_argument('--extra-deps', nargs='*', default=[], help='Additional pip dependencies (e.g., pandas matplotlib)')
  parser.add_argument('--layers', nargs='*', default=[], help='Lambda layer ARNs to attach')
  parser.add_argument('--s3-bucket', help='S3 bucket for large deployment packages (auto-created if needed)')
  args = parser.parse_args()

  session = boto3.Session(region_name=args.region)
  lambda_client = session.client('lambda')
  iam_client = session.client('iam')

  try:
    # Account id for scoping the Bedrock inference-profile ARNs below.
    account_id = session.client('sts').get_caller_identity()['Account']

    # Lambda function execution role
    lambda_role_name = args.server_name + '-role'
    lambda_trust_policy = {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Principal": {
            "Service": "lambda.amazonaws.com"
          },
          "Action": "sts:AssumeRole"
        }
      ]
    }
    lambda_permissions_policy = {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": [
              "logs:CreateLogGroup",
              "logs:CreateLogStream",
              "logs:PutLogEvents"
          ],
          "Resource": "*"
        },
        {
          # The MCP server Lambdas embed queries (Cohere Embed v4) and the
          # search server reranks (Cohere Rerank v3.5) via bedrock-runtime
          # invoke_model. Without this the Gateway-routed tool calls deploy
          # fine but fail at the FIRST embedding with AccessDenied — a failure
          # that only surfaces at invoke time, not at provisioning. Scoped to
          # the foundation-model + inference-profile ARN families (NOT region-
          # conditioned: Cohere v4 is a us.* inference profile and the editorial
          # path uses global.* profiles that route as RequestedRegion=unspecified,
          # so a region StringEquals would wrongly deny them). Mirrors the
          # InstanceRole BedrockModelInvoke statement.
          "Effect": "Allow",
          "Action": [
              "bedrock:InvokeModel",
              "bedrock:InvokeModelWithResponseStream"
          ],
          "Resource": [
              "arn:aws:bedrock:*::foundation-model/*",
              f"arn:aws:bedrock:*:{account_id}:inference-profile/*",
              f"arn:aws:bedrock:*:{account_id}:application-inference-profile/*"
          ]
        }
      ]
    }

    # Add RDS Data API permissions only if database ARNs are provided.
    # Transaction actions matter: process_return (experience server) wraps
    # ownership-check + INSERT + decrement in a single Data API transaction,
    # and ExecuteStatement alone 403s on BeginTransaction (box-verified
    # 2026-06-12 — the ONLY transactional tool, so nothing else tripped it).
    if args.db_cluster_arn:
      lambda_permissions_policy["Statement"].append({
        "Effect": "Allow",
        "Action": [
          "rds-data:ExecuteStatement",
          "rds-data:BatchExecuteStatement",
          "rds-data:BeginTransaction",
          "rds-data:CommitTransaction",
          "rds-data:RollbackTransaction",
        ],
        "Resource": args.db_cluster_arn
      })
    if args.secret_arn:
      lambda_permissions_policy["Statement"].append({
        "Effect": "Allow",
        "Action": ["secretsmanager:GetSecretValue"],
        "Resource": args.secret_arn
      })
    lambda_role_arn = create_iam_role(lambda_role_name, lambda_trust_policy, lambda_permissions_policy)

    function_name = args.server_name + '-function'

    if not os.path.exists(args.mcp_server_path):
        raise FileNotFoundError(f"MCP server file not found: {args.mcp_server_path}")

    types_path = os.path.join(os.path.dirname(args.mcp_server_path), 'common/types.py')
    if not os.path.exists(types_path):
        raise FileNotFoundError(f"Type definition file not found: {types_path}")

    # Build environment variables, only include DB vars if provided
    env_vars = {'REGION': args.region}
    if args.db_cluster_arn:
      env_vars['DB_CLUSTER_ARN'] = args.db_cluster_arn
    if args.secret_arn:
      env_vars['SECRET_ARN'] = args.secret_arn
    if args.database:
      env_vars['DATABASE'] = args.database
    # Propagate the embedding model id so the MCP Lambdas embed queries in the
    # SAME space as the seeded catalog (Cohere Embed v4). The servers default
    # to us.cohere.embed-v4:0; this just lets an operator override it centrally.
    embed_model_id = os.environ.get('BEDROCK_EMBED_MODEL_ID')
    if embed_model_id:
      env_vars['BEDROCK_EMBED_MODEL_ID'] = embed_model_id

    # Determine the target filename from handler
    target_filename = args.handler.split('.')[0] + '.py'

    lambda_function_arn = create_or_update_lambda_function(
      function_name=function_name,
      role_arn=lambda_role_arn,
      handler=args.handler,
      files={
        'common/types.py': types_path,
        target_filename: args.mcp_server_path
      },
      dependencies=['mcp'] + args.extra_deps,
      env=env_vars,
      region=args.region,
      s3_bucket=args.s3_bucket,
      layers=args.layers if args.layers else None
    )

    # Response
    response = { "role_arn": lambda_role_arn, "function_arn": lambda_function_arn }
    print(json.dumps(response, indent=2))

  except Exception as e:
    logger.error(f"Deployment failed: {str(e)}")
    sys.exit(1)

if __name__ == "__main__":
  main()