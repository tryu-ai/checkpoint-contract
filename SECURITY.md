# Security and trust

Use trusted Session factories, adapters and serializers in an isolated process.
They execute Python code; deepcopy hooks can too. Never deserialize untrusted
executable formats such as pickle. Call bounds do not stop blocking calls or
bound memory consumption; impose external time and resource limits.

Reports contain occurrence IDs and exception messages, which may expose data or
paths. Review and redact before sharing. Replay executes the embedded case in
your current environment; schema validity is not authenticity. Reports contain
no raw checkpoint state and do not prove durable storage safety.

This project has no dedicated security contact or response-time
commitment. Do not place credentials, private reports or exploit details in public
discussions. Coordinate sensitive disclosure through a private channel you have
already established with a recipient; no such channel is provisioned here.
