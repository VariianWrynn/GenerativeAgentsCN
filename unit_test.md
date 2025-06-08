# Unit Testing Guide

This document provides an overview of the unit tests in the `generative-agents` project and explains how to run them.

## Overview of Test Files

The unit tests are located in the `generative_agents/tests/` directory.

*   **`__init__.py`**:
    *   Purpose: Makes the `generative_agents/tests` directory a Python package, enabling test module discovery by the `unittest` framework.

*   **`test_start.py`**:
    *   Purpose: Tests the command-line argument parsing and initial configuration loading logic of `generative_agents/start.py`.
    *   Key Focus: Verifies handling of the `--agents_file` argument (valid/invalid files, valid/invalid agent names, default behavior) and the `--validate-config` flag.

*   **`test_llm_model.py`**:
    *   Purpose: Tests the retry and failsafe mechanisms within the `LLMModel.completion` method in `generative_agents/modules/model/llm_model.py`.
    *   Key Focus (`TestLLMModelRetryMechanisms` class): Uses a `MockLLMModel` to simulate various LLM response scenarios, testing retry logic for callback failures (parsing/validation) and exceptions from `_completion`, and ensuring failsafe values are returned after exhausting retries.

*   **`test_replay_failsafe_data.py`**:
    *   Purpose: Defines functions that generate mock raw simulation data structures. This data represents agent states resulting from LLM calls using their failsafe values (e.g., for schedule and action generation). It also includes basic structural validation of this mock data.
    *   Key Focus: Provides input data for `test_compress.py` and ensures this mock data correctly models failsafe outcomes.

*   **`test_compress.py`**:
    *   Purpose: Tests the core data transformation logic of `generative_agents/compress.py` (specifically `_process_checkpoints_to_movement_data`). Verifies that `compress.py` correctly processes raw simulation checkpoint data, including data reflecting LLM failsafe outcomes, into the `movement.json` format used by `replay.py`.
    *   Key Focus: Uses mock data from `test_replay_failsafe_data.py` to assert that compressed output accurately reflects simplified agent behavior (e.g., default schedules, generic actions) when failsafes are used.

## Running Tests

The unit tests use Python's built-in `unittest` framework. Run these commands from the root directory of the project.

### 1. Run All Tests
To discover and run all test files:
```bash
python -m unittest discover -s generative_agents/tests -p "test_*.py"
```
Alternatively, from the project root:
```bash
python -m unittest discover generative_agents/tests
```

### 2. Run a Specific Test File
To run all tests within a single file (e.g., `test_start.py`):
```bash
python -m unittest generative_agents.tests.test_start
```
*(Replace `test_start` with the desired file name, without `.py`)*

### 3. Run a Specific Test Class
To run all test methods within a specific class (e.g., `TestAgentFileArg` in `test_start.py`):
```bash
python -m unittest generative_agents.tests.test_start.TestAgentFileArg
```

### 4. Run a Specific Test Method
To run a single test method (e.g., `test_valid_agents_file` in `TestAgentFileArg` class in `test_start.py`):
```bash
python -m unittest generative_agents.tests.test_start.TestAgentFileArg.test_valid_agents_file
```
