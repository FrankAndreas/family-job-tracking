"""The family hub (FrankAndreas/family-hub): who is logged in, and the people of the job tracking app.

The hub's own client package (family-hub/client, "family-hub-client" in requirements.txt), set up with this app's key:
it asks the hub, keeps answers for a minute and knows the rules for logins from outside. The hub's tests keep it and its
fake hub (tests/fake_hub.py) in step with the hub."""

from family_hub_client import TIMEOUT_SECONDS, HubClient, HubPerson, HubUnavailable, Login, Session  # noqa: F401

client = HubClient(default_app_key="jobs")
