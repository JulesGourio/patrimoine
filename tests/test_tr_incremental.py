import asyncio

from patrimoine.sources import trade_republic as tr_mod


class FakeTR:
    """Answers the subscriptions of fetch_all from a canned timeline (newest first, 2 items per page)."""

    def __init__(self, timeline):
        self.timeline, self.asked, self._q = timeline, [], []

    def settings(self):
        return {}

    async def subscribe(self, payload):
        self.asked.append(payload)
        self._q.append((len(self.asked), payload))
        return len(self.asked)

    async def unsubscribe(self, _):
        pass

    async def recv(self):
        sub_id, p = self._q.pop(0)
        if p["type"] == "timelineTransactions":
            start = int(p["after"] or 0)
            items = self.timeline[start:start + 2]
            after = str(start + 2) if start + 2 < len(self.timeline) else None
            return sub_id, None, {"items": items, "cursors": {"after": after}}
        if p["type"] == "timelineActivityLog":
            return sub_id, None, {"items": [], "cursors": {}}
        if p["type"] == "timelineDetailV2":
            return sub_id, None, {"detail": p["id"]}
        return sub_id, None, {}

    async def close(self):
        pass


def test_second_dump_only_fetches_new_items():
    old = [{"id": f"t{i}"} for i in range(6)]
    first = asyncio.run(tr_mod.fetch_all(FakeTR(old)))
    assert len(first["transactions"]) == 6

    new = [{"id": "t_new"}] + old
    fake = FakeTR(new)
    second = asyncio.run(tr_mod.fetch_all(fake, first))
    assert [i["id"] for i in second["transactions"]][:1] == ["t_new"]
    assert len(second["transactions"]) == 7
    pages = [a for a in fake.asked if a["type"] == "timelineTransactions"]
    details = [a for a in fake.asked if a["type"] == "timelineDetailV2"]
    assert len(pages) == 2 and [d["id"] for d in details] == ["t_new"]
