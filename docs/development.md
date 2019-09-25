# Development, Build and Deploy Guide

## Build and Deploy
```bash
./run_cloudformation.sh
```

## Tests
This project use `unittest` module from `Python`

### Invoking unit tests

#### All tests
```bash
python3 -m unittest tests/*.py
```

#### All tests in single class
e.g:
```bash
python3 -m unittest tests.test_support_case_aggregator.SupportCaseAggregator
```

#### Single test
e.g:
```bash
python3 -m unittest tests.test_support_case_aggregator.SupportCaseAggregator.test_get_all_existing_cases
```
