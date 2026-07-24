# Implementation Plan: Fix HTTP 201 Auth Token

## Overview

This plan fixes the `Airflow3AuthClient.authenticate()` method to accept HTTP 201 as a
valid success response alongside HTTP 200. The implementation follows the exploration-first
bugfix workflow: write a property-based test that confirms the bug on unfixed code, apply
the minimal fix, then verify correctness and preservation.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - HTTP 201 Raises UnexpectedResponseError
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - File: `tests/airflow/test_auth_bug_exploration.py`
  - Use `hypothesis` to generate random valid `access_token` strings (`text(min_size=1)`) and `expires_at` datetime strings
  - Use `respx` to mock a 201 response with the generated token body
  - Assert that calling `client.authenticate()` raises `UnexpectedResponseError`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test PASSES on unfixed code (bug exists, so exception IS raised)
  - After the fix is applied, this test will FAIL (proving the bug is fixed — 201 no longer raises)
  - Document: on unfixed code, every generated (access_token, expires_at) pair triggers `UnexpectedResponseError(201, ...)`
  - _Requirements: 1.1, 1.2_

- [x] 2. Apply the fix to `src/drm/airflow/auth.py`

  - [x] 2.1 Implement the fix
    - Add constant `_HTTP_CREATED = 201` after `_HTTP_OK = 200`
    - Change `if response.status_code == _HTTP_OK:` to `if response.status_code in (_HTTP_OK, _HTTP_CREATED):`
    - _Bug_Condition: isBugCondition(response) where response.status_code = 201 AND body contains access_token and expires_at_
    - _Expected_Behavior: return AuthResult(token=body["access_token"], expires_at=body["expires_at"])_
    - _Preservation: HTTP 200, 401, 5xx, other codes unchanged_
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 2.2 Verify bug condition exploration test now FAILS (confirms fix works)
    - **Property 1: Expected Behavior** - HTTP 201 Returns AuthResult
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 asserts `UnexpectedResponseError` is raised for 201
    - After the fix, 201 returns `AuthResult` instead — so the test FAILS
    - This failure confirms the bug is fixed (201 is no longer rejected)
    - **EXPECTED OUTCOME**: Test FAILS (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [x] 2.3 Verify existing tests still pass (preservation)
    - **Property 2: Preservation** - Non-201 Status Code Behavior
    - **IMPORTANT**: Re-run the existing test suite in `tests/airflow/test_auth.py`
    - All existing tests for HTTP 200, 401, 5xx, network errors, timeouts must still pass
    - **EXPECTED OUTCOME**: All existing tests PASS (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Add regression test for HTTP 201 success
  - File: `tests/airflow/test_auth.py`
  - Add a test method in `TestAuthenticateSuccess` that mocks a 201 response with valid token body and asserts `AuthResult` is returned correctly
  - Verify that 201 is NOT in the parametrize list for `TestAuthenticateUnexpectedCodes` (currently it's not — just confirm)
  - _Requirements: 2.1, 2.2_

- [x] 4. Checkpoint — Ensure all tests pass
  - Run full test suite: `pytest tests/airflow/`
  - Ensure all tests pass, ask the user if questions arise.
