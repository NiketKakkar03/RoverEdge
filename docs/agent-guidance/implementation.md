# Implementation and surgical changes

- Implement only the requested behavior. Add abstractions, configuration, and flexibility only when required by that behavior or an established reuse need.
- Handle error conditions supported by the input contract or execution environment; avoid branches for states those contracts make impossible.
- Match the surrounding code's style. Keep unrelated refactoring, formatting, and comment cleanup out of the change.
- Remove imports, variables, and functions made unused by your change. Report pre-existing dead code separately rather than deleting it as incidental cleanup.
- Review the final diff: each changed line must support the request or remove an orphan created by the change.
