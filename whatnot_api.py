"""Gets sales straight from Whatnot's Seller API, instead of reading the show page.

How it works
  * The seller creates a personal access token in Whatnot's developer dashboard (with
    permission to read orders, shows and customers) and pastes it into HammerSlip.
  * A background thread asks Whatnot for the newest orders about once a second. Every
    order it hasn't seen before is a new sale: buyer username, item title(s), price, and
    whether it was an auction, Buy It Now or giveaway.
  * A label only prints once Whatnot says the payment went through. An order starts out
    unpaid; about 2 seconds later Whatnot marks it "pending_fulfillment" (paid, ready to
    ship) or "failed" (the card was declined). Failed orders are listed, never printed.
  * Orders that were already there when it started are only remembered, not printed.
  * By default only orders from a show that's live (or ended in the last 15 minutes) are
    printed, so marketplace sales outside a show don't print.

Whatnot allows about 2 requests a second per seller; this stays under that.
The token is kept in the app's settings folder (paths.settings_folder()), never in Documents.
"""
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import paths

API_BASE = (os.environ.get("HAMMERSLIP_WHATNOT_API") if not paths.IS_PACKAGED else None) \
    or "https://api.whatnot.com/seller-api/rest/v2"
TOKEN_HELP_URL = "https://developers.whatnot.com/getting-started/authentication"
SETTINGS_FILE = (Path(os.environ["HAMMERSLIP_SETTINGS_DIR"]) if os.environ.get("HAMMERSLIP_SETTINGS_DIR")
                 and not paths.IS_PACKAGED else paths.settings_folder()) / "whatnot.json"

POLL_EVERY = 1.0          # seconds between checks for new orders
MIN_GAP = 0.55            # seconds between any two requests (Whatnot allows ~2/second)
SHOWS_EVERY = 20.0        # seconds between checks of which show is live
RECENT_SHOW_GRACE = 15 * 60   # keep printing a show's orders this long after it ends
SETTLE_PER_CHECK = 6      # at most this many orders printed per check, so a rush never
                          # holds up noticing the next sales


# ---------------------------------------------------------------- settings
def load_settings():
    try:
        d = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return {"token": str(d.get("token") or ""),
                    "live_only": d.get("live_only", True) is not False}
    except (OSError, ValueError):
        pass
    return {"token": "", "live_only": True}


# ---------------------------------------------------------------- has it been paid?
# Seen on real orders: an order is created when the auction ends, then a couple of seconds
# later becomes "pending_fulfillment" (paid) or "failed" (payment declined). Later on it
# moves through shipping. Anything else is treated as "not paid yet" and checked again.
PAID = {"pending_fulfillment", "fulfilled", "shipped", "in_transit", "delivered",
        "completed", "complete", "ready_to_ship", "awaiting_shipment", "label_created"}
FAILED = {"failed", "payment_failed", "cancelled", "canceled", "refunded", "voided", "expired"}
WAIT_LIMIT = 2 * 3600          # stop waiting for a payment after this long
SHOW_WAITING_AFTER = 15        # list an order as "waiting for payment" after this many seconds


def payment_state(order):
    """ "paid", "failed" or "waiting"."""
    status = str(order.get("status") or "").lower()
    if order.get("cancelled_at") or status in FAILED or "fail" in status or "cancel" in status:
        return "failed"
    if status in PAID or any(w in status for w in ("ship", "deliver", "fulfil", "complete")):
        return "paid"
    return "waiting"


def save_settings(s):
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=1), encoding="utf-8")
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, SETTINGS_FILE)
    except OSError:
        pass


# ---------------------------------------------------------------- the API
class ApiError(Exception):
    def __init__(self, status, message, retry_after=None):
        super().__init__(message)
        self.status, self.message, self.retry_after = status, message, retry_after


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


class Client:
    def __init__(self, token):
        self.token = token.strip()
        self._last = 0.0
        self._lock = threading.Lock()

    def get(self, path, **params):
        with self._lock:                       # keep under Whatnot's rate limit
            wait = self._last + MIN_GAP - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        q = {k: ("true" if v is True else "false" if v is False else v)
             for k, v in params.items() if v is not None}
        url = API_BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/json",
            "User-Agent": f"HammerSlip/{paths.VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ssl_context()
                                        if url.startswith("https:") else None) as r:
                return json.loads(r.read(2_000_000).decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            retry = e.headers.get("Retry-After") or e.headers.get("ratelimit-reset")
            try:
                retry = float(retry) if retry else None
            except ValueError:
                retry = None
            if e.code == 401:
                raise ApiError(401, "Whatnot didn't accept the token. Check it in Whatnot API… "
                                    "(it may have been deleted or mistyped).") from e
            if e.code == 403:
                raise ApiError(403, "The token doesn't have permission for this. Give it "
                                    "read access to orders, shows and customers.") from e
            if e.code == 429:
                raise ApiError(429, "Whatnot asked us to slow down.", retry or 2) from e
            raise ApiError(e.code, f"Whatnot answered with an error ({e.code}).") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ApiError(0, "Couldn't reach Whatnot. Check your internet connection.") from e

    def me(self):
        return self.get("/users/me")

    def orders(self, limit=20, cursor=None):
        return self.get("/orders", limit=limit, cursor=cursor, reverse=True)

    def order(self, order_id):
        return self.get(f"/orders/{order_id}")

    def order_items(self, order_id):
        return self.get(f"/orders/{order_id}/items", limit=50)

    def live_shows(self):
        return self.get("/shows", status="live", limit=10)


def sale_from_order(order, items):
    """The label details for one order: {"id", "user", "title", "price", "giveaway",
    "show_id", "type", "status", "created_at"}."""
    buyer = order.get("buyer") or {}
    titles = []
    for it in items:
        t = ((it.get("purchased_item") or {}).get("title") or "").strip()
        if t:
            qty = int(it.get("quantity") or 1)
            titles.append(f"{t} (x{qty})" if qty > 1 else t)
    kind = order.get("transaction_type") or ""
    giveaway = kind == "giveaway"
    sub = ((order.get("amounts") or {}).get("subtotal") or {}).get("amount")
    price = "Giveaway" if giveaway else (f"${sub}" if sub not in (None, "") else "")
    return {"id": str(order.get("id")), "user": str(buyer.get("username") or "").strip(),
            "title": " + ".join(titles), "price": price, "giveaway": giveaway,
            "show_id": order.get("show_id"), "type": kind,
            "status": order.get("status"), "created_at": order.get("created_at")}


class Feed:
    """The background watcher. on_sale(sale_dict) for each new order once its payment is
    settled, with sale["outcome"] = "paid" (print it), "failed" (payment declined; list it,
    don't print), "waiting" (still unpaid after SHOW_WAITING_AFTER seconds; a "paid" or
    "failed" for the same id follows) or "gave_up" (never paid). on_state(text, level) when
    the connection status changes (level: "ok", "warn" or "bad"). Both are called from the
    background thread."""

    def __init__(self, token, live_only, on_sale, on_state):
        self.client = Client(token)
        self.live_only = live_only
        self.on_sale, self.on_state = on_sale, on_state
        self.stop_flag = threading.Event()
        self.seen = set()       # orders settled (or skipped): never looked at again
        self.pending = {}       # order id -> {"order", "since", "shown"}: waiting for payment
        self.live = {}          # show id -> title, for shows live now
        self.recent = {}        # show id -> time.time() it was last seen live
        self.username = None
        self._shows_at = 0.0
        self._state = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.stop_flag.set()

    def _say(self, text, level):
        if (text, level) != self._state:
            self._state = (text, level)
            self.on_state(text, level)

    # -- the loop
    def _run(self):
        backoff = 2.0
        started = False
        while not self.stop_flag.is_set():
            try:
                if not started:
                    me = self.client.me()
                    self.username = me.get("username") or me.get("display_name") or "?"
                    self._baseline()
                    started = True
                if time.monotonic() - self._shows_at > SHOWS_EVERY:
                    self._check_shows()
                self._poll()
                self._say_watching()
                backoff = 2.0
                self.stop_flag.wait(POLL_EVERY)
            except ApiError as e:
                if e.status == 401 or e.status == 403:
                    self._say(e.message, "bad")
                    self.stop_flag.wait(30)        # in case it's fixed meanwhile
                elif e.status == 429:
                    self.stop_flag.wait(max(1.0, e.retry_after or 2.0))
                else:
                    self._say(e.message + " Retrying…", "bad")
                    self.stop_flag.wait(backoff)
                    backoff = min(backoff * 2, 30)
            except Exception as e:  # noqa: BLE001
                self._say(f"Whatnot API problem: {e}. Retrying…", "bad")
                self.stop_flag.wait(backoff)
                backoff = min(backoff * 2, 30)

    def _baseline(self):
        """Remember the orders that are already there, so they don't print."""
        data = self.client.orders(limit=50).get("data") or []
        self.seen.update(str(o.get("id")) for o in data)

    def _check_shows(self):
        self._shows_at = time.monotonic()
        data = self.client.live_shows().get("data") or []
        now = time.time()
        self.live = {str(s.get("id")): (s.get("title") or "your show") for s in data}
        for sid in self.live:
            self.recent[sid] = now
        for sid, t in list(self.recent.items()):
            if now - t > RECENT_SHOW_GRACE:
                del self.recent[sid]

    def _say_watching(self):
        who = f"@{self.username}" if self.username else "your account"
        if self.live:
            title = next(iter(self.live.values()))
            self._say(f"Connected ✓  Whatnot API ({who}). Watching your live show: {title}", "ok")
        elif self.live_only:
            self._say(f"Connected ✓  Whatnot API ({who}). Waiting for your show to go live…", "ok")
        else:
            self._say(f"Connected ✓  Whatnot API ({who}). Watching all new orders.", "ok")

    def _wanted(self, order):
        if not self.live_only:
            return True
        sid = str(order.get("show_id") or "")
        return bool(sid) and (sid in self.live or sid in self.recent)

    def _poll(self):
        new, cursor, listed = [], None, {}
        for _ in range(5):        # up to 100 orders back
            page = self.client.orders(limit=20, cursor=cursor)
            data = page.get("data") or []
            for o in data:
                listed[str(o.get("id"))] = o
            fresh = [o for o in data if str(o.get("id")) not in self.seen
                     and str(o.get("id")) not in self.pending]
            new.extend(fresh)
            cursor = page.get("next_cursor")
            # Keep going while this page was all new, or while orders waiting for payment
            # are further back (so they're settled in the order they sold).
            more_new = len(fresh) == len(data)
            more_pending = any(oid not in listed for oid in self.pending)
            if not cursor or not data or not (more_new or more_pending):
                break
        if new and self.live_only and any(str(o.get("show_id") or "") not in self.live
                                          and o.get("show_id") for o in new):
            self._check_shows()   # a show may have just started
        now = time.monotonic()
        budget = [SETTLE_PER_CHECK]
        for order in reversed(new):   # oldest first, in the order they sold
            oid = str(order.get("id"))
            if not self._wanted(order):
                self.seen.add(oid)
                continue
            self.pending[oid] = {"order": order, "since": now, "shown": False}
        # Every order not settled yet, oldest first: paid, failed, or still waiting?
        for oid in sorted(self.pending, key=lambda k: (
                str(self.pending[k]["order"].get("created_at") or ""), int(k) if k.isdigit() else 0)):
            p = self.pending[oid]
            if oid in listed:
                p["order"] = listed[oid]
            elif now - p.get("checked", p["since"]) > 5:
                # Scrolled off the newest orders: look it up by itself now and then.
                p["checked"] = now
                try:
                    p["order"] = self.client.order(oid)
                except ApiError as e:
                    if e.status in (401, 403, 429):
                        raise
            self._settle(oid, p, now, budget)

    def _settle(self, oid, p, now, budget):
        order = p["order"]
        state = payment_state(order)
        if state != "waiting":
            if budget[0] <= 0:
                return            # next check (in a second) carries on with it
            budget[0] -= 1
        if state == "waiting":
            if not p["shown"] and now - p["since"] > SHOW_WAITING_AFTER:
                p["shown"] = True
                self.on_sale(dict(sale_from_order(order, self._items(oid)), outcome="waiting"))
            if now - p["since"] > WAIT_LIMIT:
                sale = sale_from_order(order, self._items(oid))
                del self.pending[oid]
                self.seen.add(oid)
                self.on_sale(dict(sale, outcome="gave_up"))
            return
        sale = sale_from_order(order, self._items(oid))   # (may raise: then it's tried again)
        del self.pending[oid]
        self.seen.add(oid)
        self.on_sale(dict(sale, outcome=state))

    def _items(self, oid):
        try:
            return self.client.order_items(oid).get("data") or []
        except ApiError as e:
            if e.status in (401, 403, 429):
                raise
            return []


def test_token(token):
    """Check a token: returns (username, warning or None). Raises ApiError."""
    c = Client(token)
    me = c.me()
    warning = None
    data = c.orders(limit=5).get("data") or []
    if data and not any((o.get("buyer") or {}).get("username") for o in data):
        warning = ("This token can't see buyer usernames, so labels would be blank. Give it "
                   "permission to read customers.")
    try:
        c.live_shows()
    except ApiError as e:
        if e.status == 403:
            warning = "This token can't read your shows. Give it permission to read shows."
        else:
            raise
    return me.get("username") or me.get("display_name") or "?", warning
