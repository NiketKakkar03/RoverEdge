# Acceptance criteria and verification

- Before changing behavior, define an observable completion criterion and the check that will establish it.
- For input validation, cover the invalid-input cases in the requested contract and confirm their expected handling.
- For a bug fix, first reproduce the failure with a focused test, then verify that the test passes after the fix.
- For a refactor, verify relevant behavior before and after the change.
- Run checks appropriate to the affected behavior. For documentation-only changes, check the edited content and local links rather than introducing code tests.
- Continue until the acceptance criteria are verified, or report the specific blocker and what remains unverified. Distinguish completed checks from proposed checks.
