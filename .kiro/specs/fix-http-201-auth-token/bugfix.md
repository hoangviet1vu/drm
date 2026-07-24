# Bugfix Requirements Document

## Introduction

The `drm login` command rejects HTTP 201 (Created) responses from the Airflow `/auth/token` endpoint, treating them as unexpected and raising an `UnexpectedResponseError`. HTTP 201 is a valid success response for token creation and should be handled identically to HTTP 200. This bug causes login failures against Airflow instances that return 201 for newly created tokens.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the Airflow `/auth/token` endpoint returns HTTP 201 with a valid token body THEN the system raises `UnexpectedResponseError` and exits with a non-zero code instead of completing login.

1.2 WHEN the Airflow `/auth/token` endpoint returns HTTP 201 THEN the system prints "Unexpected response (HTTP 201): {url}" to the user, suggesting an error occurred even though authentication succeeded server-side.

### Expected Behavior (Correct)

2.1 WHEN the Airflow `/auth/token` endpoint returns HTTP 201 with a valid JSON body containing `access_token` and `expires_at` THEN the system SHALL extract the token and expiry, return an `AuthResult`, and proceed with login (persist token and exit 0).

2.2 WHEN the Airflow `/auth/token` endpoint returns HTTP 201 with a valid JSON body THEN the system SHALL behave identically to how it handles HTTP 200 — extracting `access_token` and `expires_at` from the response body.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the Airflow `/auth/token` endpoint returns HTTP 200 with a valid token body THEN the system SHALL CONTINUE TO extract the token and expiry and return a successful `AuthResult`.

3.2 WHEN the Airflow `/auth/token` endpoint returns HTTP 401 THEN the system SHALL CONTINUE TO raise `AuthenticationError`.

3.3 WHEN the Airflow `/auth/token` endpoint returns an HTTP status code in the range 500–599 THEN the system SHALL CONTINUE TO raise `ServerError`.

3.4 WHEN the Airflow `/auth/token` endpoint returns an HTTP status code that is not 200, 201, 401, or 5xx (e.g., 403, 404, 429) THEN the system SHALL CONTINUE TO raise `UnexpectedResponseError`.

3.5 WHEN a network error or timeout occurs during the authentication request THEN the system SHALL CONTINUE TO raise `NetworkError` or `TimeoutError` respectively.
