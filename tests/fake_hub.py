"""A stand-in for the family hub in the backend tests: the hub client's own fake (family-hub/client), which answers
the client's requests as the hub does. Each person's token is "tok-<name>", from outside "cf-<name>". Invented people
only: the repository is public."""

from family_hub_client.fake import FakeHub, cloudflare_token, token  # noqa: F401

# The hub of the running test (set by conftest's autouse fixture)
current: FakeHub
