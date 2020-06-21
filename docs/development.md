# Development, Build and Deploy Guide

## Environment Prerequisites
Only python3 is supported. [https://www.python.org/doc/sunset-python-2/](Python2 has been deprecated since January 1, 2020) and we strongly urge you to use python3.

> To maintain multiple versions on python locally, use [pyenv](https://github.com/pyenv/pyenv)

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
