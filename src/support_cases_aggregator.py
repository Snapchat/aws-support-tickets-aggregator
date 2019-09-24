"""
Function that manages persistence and retrieval of AWS Support
service case information
"""

import logging
import os
from datetime import datetime, timedelta

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError

from aws_common_utils_layer import (
    get_session_with_arn,
    get_session,
    clear_empty_strings,
    set_logging_level,
)

set_logging_level()


DEFAULT_CASE_LOOKBACK_DAYS = 60

# Provide IAM role that is assumed in the member account
# where the support case was opened
ORG_SUPPORT_VIEWER_ROLE = "GetSupportInfoRole"


def list_account_ids():
    """
    Default requires permission to invoke organizations:ListAccounts API.

    DEFAULTS TO CALLING organizations:ListAccounts WITH CURRENT ROLE
    If CloudFormation stack is deployed in non-master AWS Organizations
    account, must assume role in that master AWS Organizations account.
    See README for details.
    """

    accounts = []
    assumed_role_arn = os.environ.get("ORG_MASTER_ACCOUNT_VIEWER_ROLE")
    if assumed_role_arn:
        session = get_session_with_arn(
            role_arn=assumed_role_arn, session_name="listAccountIds", base_session=None
        )
    else:
        session = boto3.session.Session()  # get local session
    try:
        client = session.client(
            "organizations", config=Config(retries={"max_attempts": 8})
        )
        paginator = client.get_paginator("list_accounts")
        response_iterator = paginator.paginate()
        for page in response_iterator:
            accounts.extend(page.get("Accounts", []))
    except (BotoCoreError, ClientError) as e:
        if e.response["Error"]["Code"] == "AccessDeniedException":
            logging.error(e)
            logging.error(
                "Could not call organizations:ListAccounts. "
                "Current account is likely not "
                "the AWS Organizations master account. "
                "See README for more details on setup. "
                "Returning empty list by default."
            )
        return []

    return [str(account_info.get("Id", "")) for account_info in accounts]


def get_all_existing_cases(recent_cases_only):
    """
    This function is called on every cron interval
    to reload the support cases DynamoDB table.
    """
    account_ids = list_account_ids()

    dynamodb_session = boto3.session.Session()
    dynamodb = dynamodb_session.resource("dynamodb")
    support_cases_table = dynamodb.Table(os.environ.get("SUPPORT_CASES_TABLE_NAME"))
    for account_id in account_ids:
        session = get_session(account_id, ORG_SUPPORT_VIEWER_ROLE, "get_support_info")
        client = session.client("support")
        if recent_cases_only:
            update_recent_cases(support_cases_table, account_id, client)
        else:
            update_all_cases(support_cases_table, account_id, client)


def update_recent_cases(
    support_cases_table, account_id, client, days=DEFAULT_CASE_LOOKBACK_DAYS
):
    """
    Only retrieve updates within last X days to avoid unnecessary duplication
    """
    kwargs = {
        "includeResolvedCases": True,
        "maxResults": 100,
        "afterTime": (datetime.now() - timedelta(days=days)).isoformat(),
    }
    update_cases_helper(support_cases_table, account_id, client, kwargs)


def update_all_cases(support_cases_table, account_id, client):
    """
    For a manual update of every case.
    """
    kwargs = {"includeResolvedCases": True, "maxResults": 100}
    update_cases_helper(support_cases_table, account_id, client, kwargs)


def update_cases_helper(support_cases_table, account_id, client, kwargs):
    """

    :param support_cases_table: DDB table name
    :param account_id: account id
    :param client: DDB session object
    :param kwargs: pagination params
    :return: None
    """
    try:
        case_response = client.describe_cases(**kwargs)
    except (ClientError, BotoCoreError) as e:
        if e.response["Error"]["Code"] == "SubscriptionRequiredException":
            logging.error("Failed subscription for account %s; ignoring", account_id)
            return
        raise e
    for case in case_response.get("cases"):
        # WARNING: recentCommunications is only the last 5 communications.
        if case.get("recentCommunications", {}).get("nextToken"):
            del case["recentCommunications"]["nextToken"]

        # put updated info into table
        case["AccountId"] = account_id
        support_cases_table.put_item(Item=case)
    if "nextToken" in case_response:
        kwargs["nextToken"] = case_response["nextToken"]
        update_cases_helper(support_cases_table, account_id, client, kwargs)


def lambda_handler(event, context):
    """
    :param event:
    Event will be either a CloudWatch Event triggered periodically,
        whose source is aws.events, or event will be the payload from
        aws_cloudtrail_process.py in the following format:
    {
        "AccountId": account_id string,
        "CaseIds": [caseid1 string, caseid2 string, etc.]
    }
    :param context:
    see https://docs.aws.amazon.com/lambda/latest/dg/python-context-object.html

    :return: None
    """
    logging.debug(context)

    logging.debug(event)
    if event.get("source") == "aws.events" or "ManualUpdate" in event:
        logging.info("Invocation to ensure support info is up-to-date")
        # Note: ensure list_account_ids() works and has proper permissions
        return get_all_existing_cases(recent_cases_only=True)
    account_id = event.get("AccountId")
    # Note: Case Id format is
    # case-ACCOUNT_NUMBER-<alphanumeric>-YEAR-<other_alphanumeric>
    # The 10-digit "Case Id" viewed from the
    # Support console is the Display Id of the case.
    case_ids = event.get("CaseIds")

    # assume role
    member_account_session = get_session(
        account_id, ORG_SUPPORT_VIEWER_ROLE, "get_support_info"
    )
    # support client has difficult in regions that aren't us-east-1 strangely
    client = member_account_session.client("support", region_name="us-east-1")

    # Use current role
    dynamodb_session = boto3.session.Session()
    dynamodb = dynamodb_session.resource("dynamodb")
    support_cases_table = dynamodb.Table(os.environ.get("SUPPORT_CASES_TABLE_NAME"))
    with support_cases_table.batch_writer() as support_table_batch:
        for case_id in case_ids:

            # get support info
            try:
                case_response = client.describe_cases(
                    caseIdList=[case_id], includeResolvedCases=True
                )
            except ClientError as e:
                logging.error("error on %s", case_id)
                if e.response["Error"]["Code"] == "SubscriptionRequiredException":
                    logging.error(
                        "Failed subscription for account %s, "
                        "need Enterprise Support; ignoring",
                        account_id,
                    )
                    support_cases_table.put_item(
                        Item={
                            "caseId": case_id,
                            "status": "** N/A; " "Must Enable Enterprise Support **",
                        }
                    )
                    continue
                raise e
            except Exception as e:
                logging.error("error on %s", case_id)
                raise e
            case = case_response.get("cases")[0]
            # WARNING: recentCommunications is only the last 5 communications.
            if case.get("recentCommunications", {}).get("nextToken"):
                del case["recentCommunications"]["nextToken"]

            clear_empty_strings(case)

            # put updated info into table
            case["AccountId"] = account_id
            support_table_batch.put_item(Item=case)

    return True
