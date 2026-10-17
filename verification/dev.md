# Domain questions — software development
- Run the tests and the build. Do tests actually exercise the behaviour they claim to, or would they pass with a broken implementation?
- Edge cases and failure paths: empty input, very large input, invalid types, network/DB failure, concurrent requests.
- Security: can a user access or change data they do not own? Is all input validated server-side? Any injection, path traversal, unsafe deserialization? Secrets in code or git?
- Does the change break existing callers or contracts (API shape, DB schema, config)?
- Migrations: reversible? Safe on existing data?
- Error handling: are errors surfaced with useful messages, or swallowed?
- Is the code more complex than the requirement needs?
