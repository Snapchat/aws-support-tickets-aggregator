#!/bin/bash

usage () {
  echo "$1, profile, stack_name, cf_s3_bucket, cf_region, ct_s3_bucket must be supplied, run script as
./run_cloudformation.sh --profile=<profile_name> --stack_name=<stack name> --cf_s3_bucket=<cloudformation s3 bucket> --cf_region=<cloudformation region> --ct_s3_bucket=<cloudtrail S3 bucket> [--template_file=<template file> --org_role=<org master role>]
where:
    --profile AWS session profile
    --stack_name AWS CloudFormation stack name to create and maintain the stack
    --cf_s3_bucket S3 bucket used as AWS SAM CloudFormation code repo
    --cf_region AWS region
    --ct_s3_bucket S3 bucket used for centralized CloudTrail events aggregation
    --template_file (Optional) AWS CloudFormation template file name (defaults to central-aggregator-cf-template.yaml)
    --org_role (Optional) Org Master account viewer role"

  exit "$2"
}

cleanup () {
  echo "cleaning up..for code $?"
  err=$?
  rm -rf build
  rm -rf layersbuild

  if [[ -f "${stack_name}"-"${some_random}".json ]]; then
    echo "removing temporary created deployment template.."
    rm -rf "${stack_name}"-"${some_random}".json
  fi

  echo "done.."

  exit ${err} # exit with same status cleanup was called
}
trap cleanup EXIT # return to original state on failure

if [[ "$#" -lt 5 ]]; then
  usage "Invalid number of arguments" 1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile=*)
      profile="${1#*=}"
      ;;
    --stack_name=*)
      stack_name="${1#*=}"
      ;;
    --cf_s3_bucket=*)
      s3_bucket="${1#*=}"
      ;;
    --cf_region=*)
      region="${1#*=}"
      ;;
    --ct_s3_bucket=*)
      cloudtrail_s3_bucket="${1#*=}"
      ;;
    --template_file=*)
      template_file="${1#*=}"
      ;;
    --org_role=*)
      org_role="${1#*=}"
      ;;
    *)
      usage "Error: Invalid arguments" 1
  esac
  shift
done



if [[ -z ${template_file+x} ]];
then
  template_file="central-aggregator-cf-template.yaml";
fi

S3_CHECK=$(aws s3api head-bucket --bucket "${s3_bucket}" --profile "${profile}" --region "${region}" --output json 2>&1)

if [[ ${S3_CHECK} = *"An error occurred"* ]]
then
  echo "$s3_bucket bucket does not exist or access denied. Aborting.."
  exit 1
fi

if [[ ${S3_CHECK} = *"config profile ($profile) could not be found"* ]]
then
  echo "$profile is invalid AWS profile. Aborting.."
  exit 1
fi

echo "This script assumes you have required permissions to create and configure AWS resources, else it will fail."
echo
echo "Using profile $profile"
echo "Using region $region"
echo "Using CloudFormation stack name as $stack_name"
echo "Using CloudFormation template '$template_file'"

some_random=$RANDOM
mkdir build
find ./src -iname '*.py' -not -iname '*_layer.py'  -exec cp '{}' './build' ';'

mkdir layersbuild
mkdir layersbuild/python

cp src/*_layer.py ./layersbuild/python

if [[ -f requirements.txt ]]
then
    echo "Looking for python dependencies"
    pip3 install -t build -r requirements.txt
fi

if [[ -z ${org_role+x} ]];
then
  org_role="";
fi

aws cloudformation package --template-file "${template_file}" --output-template-file "${stack_name}"-"${some_random}".json --s3-bucket "${s3_bucket}" --region "${region}" --profile "${profile}" --output json --use-json

aws cloudformation deploy --parameter-overrides CloudTrailBucketName="${cloudtrail_s3_bucket}" OrgListAccountsViewerRoleArn="${org_role}" --template-file "${stack_name}"-"${some_random}".json --stack-name "${stack_name}" --profile "${profile}" --region "${region}" --output json --s3-bucket "${s3_bucket}" --capabilities CAPABILITY_NAMED_IAM

aws cloudformation describe-stack-events --stack-name "${stack_name}" --profile "${profile}" --region "${region}" --output json --max-items 3

exit 0
