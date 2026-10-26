import base64
import hashlib

import pytest

from patrimoine import cloud, vault


class FakeResponse:
    def __init__(self, status: int, data: dict | None = None):
        self.status_code, self._data, self.text = status, data or {}, str(data)

    def json(self) -> dict:
        return self._data


class FakeGitHub:
    """Just enough of the git data API: refs, commits, trees and blobs, in memory."""

    def __init__(self):
        self.headers: dict = {}
        self.blobs: dict[str, str] = {}
        self.trees: dict[str, list[dict]] = {}
        self.commits: dict[str, dict] = {}
        self.refs: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def blob_sha(text: str) -> str:
        raw = text.encode()
        return hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()

    def request(self, method, url, timeout=None, json=None, params=None):
        path = url.split("/repos/JulesGourio/patrimoine/", 1)[1]
        self.calls.append((method, path))
        if method == "POST" and path == "git/trees":
            entries = []
            for e in json["tree"]:
                sha = self.blob_sha(e["content"])
                self.blobs[sha] = e["content"]
                entries.append({"path": e["path"], "type": "blob", "sha": sha})
            sha = f"tree{len(self.trees)}"
            self.trees[sha] = entries
            return FakeResponse(201, {"sha": sha})
        if method == "POST" and path == "git/commits":
            sha = f"commit{len(self.commits)}"
            self.commits[sha] = {"tree": {"sha": json["tree"]}, "parents": json["parents"]}
            return FakeResponse(201, {"sha": sha})
        if method == "PATCH" and path.startswith("git/refs/heads/"):
            name = path.removeprefix("git/refs/heads/")
            if name not in self.refs:
                return FakeResponse(422, {"message": "Reference does not exist"})
            self.refs[name] = json["sha"]
            return FakeResponse(200, {})
        if method == "POST" and path == "git/refs":
            self.refs[json["ref"].removeprefix("refs/heads/")] = json["sha"]
            return FakeResponse(201, {})
        if method == "GET" and path.startswith("git/ref/heads/"):
            name = path.removeprefix("git/ref/heads/")
            return FakeResponse(200, {"object": {"sha": self.refs[name]}}) if name in self.refs else FakeResponse(404)
        if method == "GET" and path.startswith("git/commits/"):
            return FakeResponse(200, self.commits[path.removeprefix("git/commits/")])
        if method == "GET" and path.startswith("git/trees/"):
            return FakeResponse(200, {"tree": self.trees[path.removeprefix("git/trees/")]})
        if method == "GET" and path.startswith("git/blobs/"):
            text = self.blobs[path.removeprefix("git/blobs/")]
            return FakeResponse(200, {"content": base64.b64encode(text.encode()).decode(), "encoding": "base64"})
        raise AssertionError(f"unexpected call {method} {path}")


def test_api_transport_writes_one_parentless_commit_and_reads_it_back():
    gh = FakeGitHub()
    t = cloud.ApiTransport("tok", repo="JulesGourio/patrimoine", http=gh)
    t.write_branch("donnees", {"jour.json": '{"a": 1}', "semaine.json": "{}"}, "Données")
    assert gh.headers["Authorization"] == "Bearer tok"
    first = gh.refs["donnees"]
    assert gh.commits[first]["parents"] == []

    t.write_branch("donnees", {"jour.json": '{"a": 2}'}, "Données")  # the branch now exists: force-updated
    assert gh.refs["donnees"] != first
    listing = t.list_dir("donnees", "")
    assert [p for p, _ in listing] == ["jour.json"]
    assert t.read_blob(listing[0][1]) == '{"a": 2}'


def test_api_transport_lists_only_the_folder_and_uses_git_blob_ids():
    gh = FakeGitHub()
    t = cloud.ApiTransport("tok", repo="JulesGourio/patrimoine", http=gh)
    t.write_branch("claude/analyses", {"cloud/analyses/1.json": "{}", "README.md": "x"}, "analyse")
    listing = t.list_dir("claude/analyses", "cloud/analyses")
    assert listing == [("cloud/analyses/1.json", FakeGitHub.blob_sha("{}"))]


def test_api_transport_missing_branch_is_not_an_error():
    t = cloud.ApiTransport("tok", repo="JulesGourio/patrimoine", http=FakeGitHub())
    assert t.list_dir("claude/analyses", "cloud/analyses") is None


def test_transport_uses_the_api_only_when_a_token_is_set(monkeypatch):
    monkeypatch.setattr(vault, "_backend", vault.MemoryBackend())
    assert isinstance(cloud.transport(), cloud.GitTransport)
    vault.set("github_token", "tok")
    assert isinstance(cloud.transport(), cloud.ApiTransport)


def test_api_errors_are_reported():
    class Down(FakeGitHub):
        def request(self, *a, **kw):
            return FakeResponse(500, {"message": "boom"})

    with pytest.raises(RuntimeError, match="500"):
        cloud.ApiTransport("tok", repo="JulesGourio/patrimoine", http=Down()).write_branch("donnees", {}, "x")


def test_api_transport_offline_or_bad_token_means_try_later():
    import requests

    class Offline(FakeGitHub):
        def request(self, *a, **kw):
            raise requests.ConnectionError("no network")

    class Expired(FakeGitHub):
        def request(self, *a, **kw):
            return FakeResponse(401, {"message": "Bad credentials"})

    for http in (Offline(), Expired()):
        assert cloud.ApiTransport("tok", repo="JulesGourio/patrimoine", http=http).list_dir("b", "d") is None


def test_pulls_never_run_together(monkeypatch, tmp_path):
    import threading
    import time

    from patrimoine.config import Settings

    running, overlap = [], []

    def slow(settings):
        overlap.append(bool(running))
        running.append(1)
        time.sleep(0.05)
        running.pop()
        return []

    monkeypatch.setattr(cloud, "_pull", slow)
    threads = [threading.Thread(target=cloud.pull, args=(Settings(data_dir=tmp_path),)) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert overlap == [False, False, False]
