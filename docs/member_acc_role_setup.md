#### Member Account role setup

For automatic updates, you will need an IAM role in every member account for this service to assume, in order to make `Support` API calls. 
Member account role setup [CloudFormation template](../member-acc-cf-template.yaml) can be used to create this role

```bash
aws cloudformation deploy --stack-name <stack name> --template-file member-acc-cf-template.yaml --parameter-overrides CentralAggregatorAwsAccountId=<central aggregator account id> --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM --profile aws_profile 
```

#### Example Role Policy
Above CloudFormation stack will create role with policies as shown below.

##### Role Policy Permissions:

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": [
                "support:Describe*",
                "support:"
            ],
            "Resource": "*",
            "Effect": "Allow"
        }
    ]
}
```
**Note on `support:`**: The Support API expects this permission in this specific format. Failure to include the `support:` permission will result in `botocore.exceptions.ClientError: An error occurred (AccessDeniedException) when calling the DescribeCases operation: User: arn:aws:sts::ACCOUNT_ID:assumed-role/GetSupportInfoRole/get_support_info is not authorized to perform: support:`. Alternatively, you may choose to provide `GetSupportInfoRole` with the broader `support:*` permission to allow all support actions.

##### Role Trust Relationships:

```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustSupportViewer",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::CentralAggregatorAwsAccountId:role/SupportAggregator"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```