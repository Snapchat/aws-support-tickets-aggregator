#### AWS Organizations Master Account role setup

Org master setup [CloudFormation template](../org-master-cf-template.yaml) can be used to create requisite role 
when your setup has separate Central Aggregator and Master accounts.

```bash
aws cloudformation deploy --stack-name <stack name> --template-file org-master-cf-template.yaml --parameter-overrides CentralAggregatorAwsAccountId=<central aggregator account id> --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM --profile aws_profile 
```

You may use any name in the `<stack name>` parameter (e.g. `master-acct-support`).

#### Example Role Policy
Above CloudFormation stack will create role with policies as shown below.

##### Role Policy Permissions:

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": [
                "organizations:ListAccounts"
            ],
            "Resource": "*",
            "Effect": "Allow"
        }
    ]
}
```

##### Role Trust Relationships:

```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustSupportAggregator",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::CentralAggregatorAwsAccountId:role/SupportAggregator"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```