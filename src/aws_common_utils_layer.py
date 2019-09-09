"""
Utilities needed to perform common AWS related tasks like getting sessions,
unzipping notifications received from S3 etc.

Typically this file can be part of AWS Lambda layer package
"""

import json
import logging
import os
import urllib
from gzip import GzipFile
from io import BytesIO

import boto3
from botocore.exceptions import ClientError, BotoCoreError

# see RoleSessionName in
# https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html
SESSION_NAME_MIN_LENGTH = 2
SESSION_NAME_MAX_LENGTH = 64


def handle_session_name_length(session_name):
    """
    Comply to role session name limitation of 64 characters
    https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-limits.html

    :param session_name: role session name
    :return: session_name (truncated to 64 if needed)
    """
    if len(session_name) > SESSION_NAME_MAX_LENGTH:
        logging.info(
            "session name was too long; truncating to %s", SESSION_NAME_MAX_LENGTH
        )
        return session_name[:SESSION_NAME_MAX_LENGTH]

    return session_name


def get_session_with_arn(role_arn, session_name, base_session):
    """
    Returns a boto3.session.Session that assumed role_arn from base_session.

    base_session is the session used to assume the role;
        it must have permissions to assume the role.
    By default, base_session is the caller's regular boto3 session.
    """
    if not base_session:
        base_session = boto3.Session()

    if not session_name:
        session_name = "aws_common_utils"

    session_name = handle_session_name_length(session_name)
    client = base_session.client("sts")

    try:
        response = client.assume_role(RoleArn=role_arn, RoleSessionName=session_name)

        access_key = response["Credentials"]["AccessKeyId"]
        secret = response["Credentials"]["SecretAccessKey"]
        session_token = response["Credentials"]["SessionToken"]

        return boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret,
            aws_session_token=session_token,
        )
    except (BotoCoreError, ClientError) as e:
        logging.error(
            "get_session_with_arn() failed trying to assume %s \
                       due to clienterror or botocore error",
            role_arn,
        )
        logging.error(str(e))
        raise e


def get_session(account_id, role_name, session_name):
    """
    Returns a boto3.session.Session for account_id that assumes role_name role.

    base_session is the session used to assume the role;
        it must have permissions to assume the role.
    By default, base_session is the caller's regular boto3 session.
    """

    return get_session_with_arn(
        "arn:aws:iam::{}:role/{}".format(account_id, role_name), session_name, None
    )


def clear_empty_strings(data):
    """
    Remove empty string values from data structs.
    For dict, deletes the empty string value and any corresponding key.
    Since dicts are passed as references, dict changes are also in-place.

    Returns the modified version of the data.
    """
    if isinstance(data, dict):
        for k, v in data.items():
            if v == "":
                del data[k]
            else:
                data[k] = clear_empty_strings(v)
    elif isinstance(data, (list, set, tuple)):
        # use list comprehension to filter out "" and modify items,
        # then reconstruct as original data type
        data = type(data)([clear_empty_strings(x) for x in data if x != ""])
    elif data == "":
        return None
    return data


def _is_s3_notif(event):
    """
    Check if type is S3 notification

    :param event:
    :return: True/False
    """
    return (
        event.get("Records")
        and isinstance(event.get("Records"), list)
        and "s3" in event.get("Records")[0]
    )


def get_gzipped_s3_objects_from_sns_msg_of_dict(session, event):
    """
    get_s3_objects_from_sns_msg_of_dict() but with a predefined
    object_handler_function that unzips gzipped objects
    and converts them to dicts.

    Will also detect if a regular S3 notif was received instead
    of an SNS dict and forward to appropriate getter function.
    """
    objects = []
    if _is_s3_notif(event):
        return get_gzipped_s3_objects_from_dict(session, event)
    for record in event.get("Records", []):
        message = record.get("Sns", {}).get("Message")
        objects.extend(get_gzipped_s3_objects_from_dict(session, json.loads(message)))
    return objects


def default_unzip_s3_object_handler_function(response):
    """
    Utility to unzip S3 object
    """
    bytestream = BytesIO(response["Body"].read())
    raw_object = GzipFile(None, "rb", fileobj=bytestream).read()
    try:
        # decode if allowed
        return_object = raw_object.decode("utf-8")
    except AttributeError:
        return_object = raw_object
    return json.loads(return_object)


def get_gzipped_s3_objects_from_dict(session, event):
    """
    get_s3_objects_from_dict() but with a predefined object_handler_function
    that unzips gzipped objects and converts them to dicts.
    """
    return get_s3_objects_from_dict(
        session, event, default_unzip_s3_object_handler_function
    )


def get_s3_objects_from_dict(session, event, object_handler_function):
    """
    Given a dict (e.g. event, notification), return a list of all
        the S3 objects mentioned in the dict.
    object_handler_function(response) will decode the s3 get_object
        API response for every object.
    By default, object_handler_function treats response["Body"] as a
        JSON string and loads it as a dict.
    """

    objects = []
    s3 = session.client("s3")
    # Get the object from the event and show its content type
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        unprocessed_key = record["s3"]["object"]["key"]
        # urllib changes structure and encoding is different
        # between python 2 and 3
        key = (
            urllib.parse.unquote_plus(unprocessed_key)
            # if sys.version_info[0] >= 3
            # else urllib.unquote_plus(unprocessed_key.encode("utf-8"))
        )
        logging.info("Bucket: %s. Key: %s", bucket, key)

        # get S3 object and add it to return list
        response = s3.get_object(Bucket=bucket, Key=key)
        objects.append(object_handler_function(response))
    return objects


def set_logging_level(
    manually_set_level=None, environment_variable_key="LOGGING_LEVEL"
):
    """
    Set logging level according to whatever value is stored in the environment
    variable. Order of "if" checks is prioritized by anticipated frequency
    of use. See actual levels here:
    https://docs.python.org/3/library/logging.html#levels
    Provide value for either environment_variable_key or manually_set_level,
    not both. Defaults to using environment_variable_key 'LOGGING_LEVEL'
    If providing manually_set_level, please provide the string (e.g. "INFO"),
    not the class (e.g. logging.INFO)

    Returns logger object
    """
    logger = logging.getLogger()
    level = (
        os.environ.get(environment_variable_key)
        if environment_variable_key
        else manually_set_level
    )
    if level == "INFO":
        logger.setLevel(logging.INFO)
    elif level == "ERROR":
        logger.setLevel(logging.ERROR)
    elif level == "WARNING":
        logger.setLevel(logging.WARNING)
    elif level == "DEBUG":
        logger.setLevel(logging.DEBUG)
    elif level == "CRITICAL":
        logger.setLevel(logging.CRITICAL)
    else:
        logging.error("Received level of %s, defaulting to NOTSET", level)
        logger.setLevel(logging.NOTSET)
    return logger
