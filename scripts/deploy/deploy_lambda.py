import boto3
import io
import json
import os
import sys
import time
import zipfile
import tempfile
import argparse
import shutil
import logging
import urllib.request
from subprocess import run as Run
from pathlib import Path
import re

logger = logging.getLogger(__name__)

# The Python the function runs, and the one its dependencies are installed for: the
# same 3.14 the box, the Runtime and requirements.lock use.
LAMBDA_PYTHON = '3.14'

iam_client = None
lambda_client = None


def _region_from_arn(arn: str, fallback: str) -> str:
  match = re.match(r"^arn:[^:]+:[^:]+:([^:]+):", arn or "")
  return match.group(1) if match else fallback

def create_iam_role(role_name, trust_policy, policy_document, tags=None):
  try:
      # Create role
      response = iam_client.create_role(
          RoleName=role_name,
          AssumeRolePolicyDocument=json.dumps(trust_policy),
          Tags=[{"Key": key, "Value": value} for key, value in (tags or {}).items()],
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
      if tags:
        iam_client.tag_role(
          RoleName=role_name,
          Tags=[{"Key": key, "Value": value} for key, value in tags.items()],
        )

      # Attach inline policy
      iam_client.put_role_policy(
          RoleName=role_name,
          PolicyName=f"{role_name}-policy",
          PolicyDocument=json.dumps(policy_document)
      )
      
      # Wait for role to be available
      time.sleep(10)

      return response['Role']['Arn']

def build_package(files, dependencies):
  """Return the deployment zip's bytes: `files` (zip path -> source) plus `dependencies`."""
  with tempfile.TemporaryDirectory() as temp_dir:
    for target_name, source_path in files.items():
      file_path = Path(temp_dir) / target_name
      file_path.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(source_path, file_path)
      logger.info(f"Added file to package: {target_name}")

    if dependencies:
      logger.info(f"Installing dependencies: {', '.join(dependencies)}")
      for dep in dependencies:
        Run(['uv', 'pip', 'install', dep, '--target', temp_dir,
             '--python-platform', 'linux', '--python-version', LAMBDA_PYTHON, '--quiet'], check=True)

    zip_path = f"{temp_dir}_deployment.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
      for root, dirs, files_in_dir in os.walk(temp_dir):
        for file in files_in_dir:
          file_path = os.path.join(root, file)
          arcname = os.path.relpath(file_path, temp_dir)
          zipf.write(file_path, arcname)

    with open(zip_path, 'rb') as f:
      zip_content = f.read()
    os.remove(zip_path)
    return zip_content


def create_or_update_lambda_function(function_name, role_arn, handler, files, dependencies, env, region, s3_bucket=None, layers=None, tags=None):
  try:
      zip_content = build_package(files, dependencies)
      zip_size_mb = len(zip_content) / (1024 * 1024)
      logger.info(f"Created deployment package: {zip_size_mb:.1f} MB")

      # Use S3 if package > 50MB or bucket specified
      use_s3 = zip_size_mb > 50 or s3_bucket
      code_config = None
      
      if use_s3:
        if not s3_bucket:
          # Create temp bucket
          account_id = boto3.client('sts', region_name=region).get_caller_identity()['Account']
          s3_bucket = f"lambda-deploy-{account_id}-{region}"
          s3_client = boto3.client('s3', region_name=region)
          try:
            if region == 'us-east-1':
              s3_client.create_bucket(Bucket=s3_bucket)
            else:
              s3_client.create_bucket(Bucket=s3_bucket, CreateBucketConfiguration={'LocationConstraint': region})
            logger.info(f"Created S3 bucket: {s3_bucket}")
            if tags:
              s3_client.put_bucket_tagging(
                Bucket=s3_bucket,
                Tagging={"TagSet": [
                  {"Key": key, "Value": value} for key, value in tags.items()
                ]},
              )
          except s3_client.exceptions.BucketAlreadyOwnedByYou:
            pass
          except s3_client.exceptions.BucketAlreadyExists:
            pass
        
        workshop_id = (tags or {}).get("PellierWorkshopId", "unknown")
        s3_key = f"lambda/{workshop_id}/{function_name}.zip"
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
      
      # 'Runtime' is the Lambda managed-runtime identifier; the package's
      # dependencies are installed for the same version (build_package).
      config_params = {
        'FunctionName': function_name, 'Runtime': f'python{LAMBDA_PYTHON}', 'Role': role_arn, 'Handler': handler,
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

      if tags:
        lambda_client.tag_resource(Resource=function_arn, Tags=tags)

      return function_arn
      
  except Exception as e:
    logger.error(f"Failed to create/update Lambda function {function_name}: {str(e)}")
    raise


# Bootstrap packages this Lambda once, from the checkout participants start
# with, so Lab 1's search modules ship from their solution copies: each is its
# live module plus the answers inside the marked regions. A participant deploy
# (Labs 3 and 4) then swaps in the participant's own two modules once both Lab 1
# checks pass, and the supplied ones while either does not
# (`provision_agentcore_end_to_end._ship_lab1_search`), so a half-finished Lab 1
# never reaches the Gateway. Lab 3B's build fingerprint digests the Runtime
# package, not this zip; `tests/test_lambda_package.py` keeps the two apart.
SOLUTION_COPIES = {
  'services/store_tools.py': '../../solutions/the-quiet-search/retrieval/store_tools_solution.py',
  'services/search_plan.py': '../../solutions/the-quiet-search/retrieval/search_plan_solution.py',
}

# Published zip path -> repository source, relative to the server entrypoint's
# directory (scripts/deploy). `tests/test_lambda_shared_helpers.py` asserts
# every module the server imports is listed here.
SHARED_MODULES = {
  'common/types.py': 'common/types.py',
  'common/dataapi.py': 'common/dataapi.py',
  'common/handler.py': 'common/handler.py',
  'gateway_tool_schemas.py': 'gateway_tool_schemas.py',
  'services/__init__.py': '../../pellier/backend/services/__init__.py',
  'services/store_tools.py': SOLUTION_COPIES['services/store_tools.py'],
  'services/retrieval_receipt.py': '../../pellier/backend/services/retrieval_receipt.py',
  'services/search_plan.py': SOLUTION_COPIES['services/search_plan.py'],
  'services/catalog_vocabulary.py': '../../pellier/backend/services/catalog_vocabulary.py',
}


def shared_module_paths(mcp_server_path):
  """Resolve `SHARED_MODULES` against the directory holding the server file."""
  shared_dir = os.path.dirname(os.path.abspath(mcp_server_path))
  return {
    target: os.path.normpath(os.path.join(shared_dir, source))
    for target, source in SHARED_MODULES.items()
  }


def package_files(mcp_server_path, handler):
  """The zip's file map: every shared module plus the server entrypoint.

  Checked here rather than discovered at cold start: a missing entry is a
  ModuleNotFoundError on the first Gateway call, long after the deploy
  reported success.
  """
  files = {}
  for module, module_path in shared_module_paths(mcp_server_path).items():
    if not os.path.exists(module_path):
      raise FileNotFoundError(f"Shared module not found: {module_path}")
    files[module] = module_path
  files[handler.split('.')[0] + '.py'] = mcp_server_path
  return files


def replace_package_modules(client, function_name, modules):
  """Swap modules inside a deployed package and publish it, without rebuilding it.

  ``modules`` maps a path inside the zip to a local file. Only those entries change:
  the dependencies and every other module stay byte for byte. Returns ``False`` when
  the package already carries those exact files, so nothing is uploaded.
  """
  location = client.get_function(FunctionName=function_name)['Code']['Location']
  with urllib.request.urlopen(location, timeout=120) as response:
    deployed = zipfile.ZipFile(io.BytesIO(response.read()))
  wanted = {name: Path(path).read_bytes() for name, path in modules.items()}
  if all(name in deployed.namelist() and deployed.read(name) == data
         for name, data in wanted.items()):
    return False
  rebuilt = io.BytesIO()
  with zipfile.ZipFile(rebuilt, 'w', zipfile.ZIP_DEFLATED) as target:
    for item in deployed.infolist():
      if item.filename not in wanted:
        target.writestr(item, deployed.read(item.filename))
    for name, data in wanted.items():
      info = zipfile.ZipInfo(name, time.localtime()[:6])
      info.compress_type = zipfile.ZIP_DEFLATED
      info.external_attr = 0o644 << 16  # readable by the Lambda runtime's user
      target.writestr(info, data)
  client.update_function_code(FunctionName=function_name, ZipFile=rebuilt.getvalue())
  client.get_waiter('function_updated_v2').wait(FunctionName=function_name)
  return True


def main():
  global iam_client, lambda_client
  # Here, not at import: the participant deploy imports this module, and a root
  # handler there would print every library's INFO lines into the lab terminal.
  logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

  parser = argparse.ArgumentParser(description="Deploy Lambda function to AWS")
  parser.add_argument('--region', help="AWS Region to use.", default=os.getenv("AWS_REGION", "us-east-1"))
  parser.add_argument('--server-name', default='pellier-store-tools-server', help='The name of the server deployed by this function.')
  parser.add_argument('--db-cluster-arn', help="Aurora PostgreSQL DB cluster ARN")
  parser.add_argument('--db-region', help="AWS Region for the Aurora Data API endpoint")
  parser.add_argument('--secret-arn', help="AWS Secrets Manager secret ARN")
  parser.add_argument('--database', help="The name of the database to connect to", default="postgres")
  parser.add_argument('--mcp-server-path', default='./', help='Path to the MCP server entrypoint file.')
  parser.add_argument('--handler', default='pellier_store_tools.lambda_handler', help='Lambda handler function')
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
    workshop_tags = {
      "Project": "pellier",
      "PellierWorkshopId": os.environ.get("WORKSHOP_ID", "").strip() or "dat416",
    }

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
          # The store-tools Lambda embeds queries (Cohere Embed v4) through
          # InvokeModel and calls the separate Rerank API for Cohere Rerank
          # v3.5. Without both actions, Gateway-routed search deploys cleanly
          # but silently falls back to RRF at invocation time.
          # Scoped to
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
        },
        {
          # bedrock:Rerank does not support resource-level permissions. IAM
          # evaluates it against "*" even when the request names a specific
          # reranking model ARN, so it must be isolated from the scoped
          # InvokeModel statement above.
          "Effect": "Allow",
          "Action": ["bedrock:Rerank"],
          "Resource": "*"
        }
      ]
    }

    # Add RDS Data API permissions only if database ARNs are provided. The
    # transaction actions stay granted so a tool that opens a Data API
    # transaction does not 403 on BeginTransaction (box-verified 2026-06-12).
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
    lambda_role_arn = create_iam_role(
      lambda_role_name,
      lambda_trust_policy,
      lambda_permissions_policy,
      tags=workshop_tags,
    )

    function_name = args.server_name + '-function'

    if not os.path.exists(args.mcp_server_path):
        raise FileNotFoundError(f"MCP server file not found: {args.mcp_server_path}")

    # Every module the store-tools server imports, staged at the path it is
    # imported from. The `services/` entries are the one tool implementation
    # the backend's @tool wrappers call too, plus the two pure retrieval
    # modules it imports; none of them import the backend's settings, so they
    # run unchanged in the zip.
    files = package_files(args.mcp_server_path, args.handler)

    # Build environment variables, only include DB vars if provided
    db_region = args.db_region or _region_from_arn(args.db_cluster_arn, args.region)
    env_vars = {'REGION': args.region, 'DB_REGION': db_region}
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

    lambda_function_arn = create_or_update_lambda_function(
      function_name=function_name,
      role_arn=lambda_role_arn,
      handler=args.handler,
      files=files,
      dependencies=['mcp==1.30.0'] + args.extra_deps,
      env=env_vars,
      region=args.region,
      s3_bucket=args.s3_bucket,
      layers=args.layers if args.layers else None,
      tags=workshop_tags,
    )

    # Response
    response = { "role_arn": lambda_role_arn, "function_arn": lambda_function_arn }
    print(json.dumps(response, indent=2))

  except Exception as e:
    logger.error(f"Deployment failed: {str(e)}")
    sys.exit(1)

if __name__ == "__main__":
  main()
