"""A stand-in for the family hub in the backend tests: who is logged in, and the app's people (spec 2026-10-30).

Each person's token is "tok-<name>". Invented people only: the repository is public."""

from app import hub, hub_people


class FakeHub:
    def __init__(self):
        self.people: dict[str, hub.HubPerson] = {}
        self.access: set[str] = set()
        self.down = False
        # The app's tile shares the people's confirmed e-mail addresses (and which ones the people have)
        self.share_email = False
        self.emails: dict[str, str] = {}
        self._next_id = 1

    def _changed(self) -> None:
        hub.forget()
        hub_people.forget()

    def add(self, name: str, role: str = "PARENT", access: bool = True, language: str = "de") -> str:
        """A person in the hub (with access to the budget app unless access=False); returns their token."""
        self.people[name] = hub.HubPerson(id=self._next_id, name=name, role=role, color=None, language=language)
        self._next_id += 1
        if access:
            self.access.add(name)
        self._changed()
        return token(name)

    def give_access(self, name: str) -> None:
        self.access.add(name)
        self._changed()

    def remove_access(self, name: str) -> None:
        self.access.discard(name)
        self._changed()

    def rename(self, old: str, new: str) -> None:
        person = self.people.pop(old)
        self.people[new] = hub.HubPerson(person.id, new, person.role, person.color, person.language)
        if old in self.access:
            self.access.discard(old)
            self.access.add(new)
        self._changed()

    def set_role(self, name: str, role: str) -> None:
        person = self.people[name]
        self.people[name] = hub.HubPerson(person.id, name, role, person.color, person.language)
        self._changed()

    def set_language(self, name: str, language: str) -> None:
        person = self.people[name]
        self.people[name] = hub.HubPerson(person.id, name, person.role, person.color, language)
        self._changed()

    def _person(self, tok: str):
        # From outside the app passes Cloudflare's token on (as "cf:<token>"); the hub knows the person by it
        if tok.startswith("cf:"):
            return next((p for name, p in self.people.items() if cloudflare_token(name) == tok[3:]), None)
        return next((p for name, p in self.people.items() if token(name) == tok), None)

    # The two calls the app makes, in place of hub.fetch_session and hub.fetch_people
    def fetch_session(self, tok: str):
        if self.down:
            raise hub.HubUnavailable("down")
        person = self._person(tok)
        if person is None:
            return None, False
        return person, person.name in self.access

    def fetch_people(self, tok: str):
        if self.down:
            raise hub.HubUnavailable("down")
        person = self._person(tok)
        if person is None or person.name not in self.access:
            return []
        found = sorted((self.people[name] for name in self.access), key=lambda p: p.name.casefold())
        if not self.share_email:
            return found
        return [
            hub.HubPerson(p.id, p.name, p.role, p.color, p.language, email=self.emails.get(p.name), email_shared=True)
            for p in found
        ]


def token(name: str) -> str:
    return f"tok-{name}"


def cloudflare_token(name: str) -> str:
    """What Cloudflare Access sends as Cf-Access-Jwt-Assertion after the person's e-mail code (outside)."""
    return f"cf-{name}"


# The hub of the running test (set by conftest's autouse fixture)
current = FakeHub()
