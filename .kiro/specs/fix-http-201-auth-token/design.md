# Fix HTTP 201 Auth Token — Bugfix Design

## Overview

The `Airflow3AuthClient.authenticate()` method only accepts HTTP 200 as a success response when exchanging credentials for a JWT via `POST /auth/token`. Airflow instances that return HTTP 201 (Created) for newly minted tokens cause an `UnexpectedResponseError`, failing the login even though the server successfully authenticated the user. The fix widens the success condition to accept both 200 and 201.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — the Airflow server returns HTTP 201 with a valid token body
- **Property (P)**: The desired behavior when HTTP 201 is received — extract `access_token` and `expires_at`, return an `AuthResult`
- **Preservation**: Existing behavior for HTTP 200, 401, 5xx, and other status codes that must remain unchanged
- **`Airflow3AuthClient.authenticate()`**: The method in `src/drm/airflow/auth.py` that posts credentials and interprets the response
- **`_HTTP_OK`**: Existing constant (`200`) used in the success condition

## Bug Details

### Bug Condition

The bug manifests when the Airflow `/auth/token` endpoint returns HTTP 201 instead of HTTP 200. The `authenticate()` method only checks `response.status_code == _HTTP_OK` for success, so any other 2xx code falls through to the final `raise UnexpectedResponseError(...)`.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type HttpResponse from POST /auth/token
  OUTPUT: boolean

  RETURN input.status_code = 201
         AND input.json_body IS NOT NULL
         AND input.json_body contains "access_token"
         AND input.json_body contains "expires_at"
END FUNCTION
```

### Examples

- Server returns `201 {"access_token": "jwt-abc", "expires_at": "2026-01-01T00:00:00+00:00"}` → current code raises `UnexpectedResponseError(201, url)` instead of returning `AuthResult`
- Server returns `201 {"access_token": "", "expires_at": ""}` → current code raises `UnexpectedResponseError` instead of returning `AuthResult(token="", expires_at="")`
- Server returns `200 {"access_token": "jwt-abc", ...}` → handled correctly (not a bug condition)
- Server returns `201` with no JSON body → would still raise `UnexpectedResponseError` (acceptable; body is malformed)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- HTTP 200 with valid token body continues to return `AuthResult`
- HTTP 401 continues to raise `AuthenticationError`
- HTTP 500–599 continues to raise `ServerError`
- HTTP 403, 404, 429, and other unexpected codes continue to raise `UnexpectedResponseError`
- Network errors and timeouts continue to raise `NetworkError` and `TimeoutError`

**Scope:**
All inputs where `status_code != 201` are completely unaffected by this fix. The only behavioral change is for responses with `status_code == 201`.

## Hypothesized Root Cause

The root cause is a narrow equality check in `src/drm/airflow/auth.py`:

```python
if response.status_code == _HTTP_OK:
    # extract token
```

This only matches `200`. HTTP 201 is semantically valid for resource creation (the token is a new resource) but was not anticipated when the client was written.

## Correctness Properties

Property 1: Bug Condition - HTTP 201 Returns AuthResult

_For any_ HTTP response with status code 201 and a JSON body containing `access_token` and `expires_at` fields, the fixed `authenticate()` method SHALL extract those fields and return an `AuthResult` with `token` and `expires_at` populated from the response body, without raising any exception.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Non-201 Status Code Behavior

_For any_ HTTP response where the status code is NOT 201 (i.e., 200, 401, 5xx, or other unexpected codes), the fixed `authenticate()` method SHALL produce exactly the same result as the original method — returning `AuthResult` for 200, raising `AuthenticationError` for 401, raising `ServerError` for 5xx, and raising `UnexpectedResponseError` for all other codes.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

**File**: `src/drm/airflow/auth.py`

**Function**: `authenticate()`

**Specific Changes**:
1. **Add constant**: Add `_HTTP_CREATED = 201` alongside `_HTTP_OK = 200`
2. **Widen success condition**: Change `if response.status_code == _HTTP_OK:` to `if response.status_code in (_HTTP_OK, _HTTP_CREATED):`

No other files require changes. The fix is a two-line change that extends the set of accepted success codes.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, write a property-based exploration test that demonstrates the bug on the current (unfixed) code, then apply the fix and verify both correctness and preservation.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm that HTTP 201 responses with valid token bodies raise `UnexpectedResponseError`.

**Test Plan**: Use `hypothesis` to generate random valid `access_token` strings and `expires_at` values. Mock a 201 response using `respx`. Assert that `UnexpectedResponseError` is raised. Run on UNFIXED code to confirm the bug exists.

**Test Cases**:
1. **Random valid tokens**: Generate arbitrary non-empty `access_token` and ISO date `expires_at`, mock 201, assert `UnexpectedResponseError` raised (will fail after fix)

**Expected Counterexamples**:
- `authenticate()` raises `UnexpectedResponseError(201, endpoint)` for every generated input

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL (access_token, expires_at) WHERE isBugCondition(response(201, access_token, expires_at)) DO
  result := authenticate_fixed(url, username, password)
  ASSERT result.token = access_token
  ASSERT result.expires_at = expires_at
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL response WHERE NOT isBugCondition(response) DO
  ASSERT authenticate_original(response) = authenticate_fixed(response)
END FOR
```

**Testing Approach**: The existing test suite (`tests/airflow/test_auth.py`) already covers HTTP 200, 401, 5xx, network errors, and timeouts. Adding HTTP 201 to `TestAuthenticateSuccess` and ensuring 201 is excluded from `TestAuthenticateUnexpectedCodes` provides concrete preservation evidence. The existing parametrized tests serve as preservation tests.

**Test Cases**:
1. **HTTP 200 still works**: Existing tests cover this (preservation)
2. **HTTP 401 still raises**: Existing tests cover this (preservation)
3. **HTTP 5xx still raises**: Existing tests cover this (preservation)
4. **HTTP 201 regression test**: New test in `TestAuthenticateSuccess` that mocks 201 and asserts `AuthResult`

### Unit Tests

- Test HTTP 201 response returns `AuthResult` (new)
- Existing tests for 200, 401, 5xx, network errors (preservation — already pass)

### Property-Based Tests

- Generate random `access_token` and `expires_at` values, mock 201, assert `UnexpectedResponseError` raised (exploration — confirms bug on unfixed code)
- After fix: same test asserts `AuthResult` returned correctly

### Integration Tests

- Full `drm login` flow against a mocked 201 endpoint (future scope — not required for this minimal fix)
