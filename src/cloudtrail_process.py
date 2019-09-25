"""
Function that receives and processes CloudTrail events via S3 object
creation notifications
"""

import json
import logging
import os
from collections import defaultdict

import boto3
from aws_common_utils_layer import (
    get_gzipped_s3_objects_from_sns_msg_of_dict,
    set_logging_level,
)

set_logging_level()


def lambda_handler(event, context):
    """
    How is it invoked?:
    This lambda will take in an s3 notification from the CloudTrail
        bucket that was sent via SNS and fetch the S3 object.

    The purpose of this pattern for the SNS topic is to fan out
    CloudTrail events processing, as CT events may be used for other purposes.

    :param event:
    https://docs.aws.amazon.com/AmazonS3/latest/
    dev/notification-content-structure.html

    :param context:
    https://docs.aws.amazon.com/lambda/latest/dg/python-context-object.html

    :return: None
    """

    logging.debug(context)

    session = boto3.session.Session()
    try:
        objects = get_gzipped_s3_objects_from_sns_msg_of_dict(session, event)
    except ValueError as e:
        logging.warning("Retrieved non-JSON object %s", str(e))
        return

    logging.info("Retrieved S3 objects:\n%s", objects)

    support_cases_to_check = defaultdict(set)

    for obj in objects:
        for record in obj.get("Records", []):
            account_id = record.get("recipientAccountId")
            event_name = record.get("eventName")

            # Support Cases
            # Currently not including event AddAttachmentsToSet
            # Including AddCommunicationToCase to cover when case is reopened
            if event_name in ["CreateCase", "ResolveCase", "AddCommunicationToCase"]:
                case_id = record.get("responseElements", {}).get(
                    "caseId"
                ) or record.get("requestParameters", {}).get("caseId")

                if case_id:
                    logging.info(
                        "%s: Support case %s found with event %s",
                        account_id,
                        case_id,
                        event_name,
                    )
                    support_cases_to_check[account_id].add(case_id)
                else:
                    logging.error(
                        "CaseIdMissingError %s: \
                        Support case without caseId found with event %s; %s",
                        account_id,
                        event_name,
                        record,
                    )

    # Invoke Support Case Lambda to aggregate support case info
    client = session.client("lambda")
    for account_id, case_ids in support_cases_to_check.items():
        cases = list(case_ids)
        client.invoke(
            FunctionName=os.environ["SUPPORT_CASES_AGGREGATOR_LAMBDA_NAME"],
            InvocationType="Event",
            Payload=json.dumps({"AccountId": account_id, "CaseIds": cases}),
        )
