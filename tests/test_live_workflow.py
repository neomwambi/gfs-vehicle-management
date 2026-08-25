"""End-to-end workflow smoke test against a running local server."""

from __future__ import annotations

import base64
import sys
from datetime import datetime, timedelta

import httpx

BASE = "http://127.0.0.1:8001"
PASS = 0
FAIL = 0


def ok(name: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {name}")


def fail(name: str, detail: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL  {name}: {detail}")


def client_for(username: str) -> tuple[httpx.Client, dict]:
    c = httpx.Client(base_url=BASE, timeout=30.0)
    r = c.post("/api/auth/login", json={"Username": username})
    r.raise_for_status()
    data = r.json()
    c.headers["X-Session-Token"] = data["session_token"]
    return c, data["user"]


def tiny_jpeg_data_url() -> str:
    # Minimal valid JPEG (1x1 pixel)
    jpeg = base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
        "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
        "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIA"
        "AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEB"
        "AQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAGfAP/E"
        "ABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAQUCf//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAI"
        "AQMBAT8Bf//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQIBAT8Bf//EABQQAQAAAAAAAAAAAAAAAA"
        "AAAAD/2gAIAQEABj8Cf//EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAT8hf//Z"
    )
    # Use a slightly larger payload so storage size check (>=100 bytes) passes
    raw = jpeg + (b"\x00" * 120)
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def five_photos() -> list[dict]:
    url = tiny_jpeg_data_url()
    return [{"angle": a, "data_url": url} for a in ("front", "back", "left", "right", "odometer")]


def main() -> int:
    print("=== GFS Vehicle Management - live API test ===\n")

    # --- Auth ---
    print("[1] Auth & RBAC")
    try:
        thabo, u_thabo = client_for("omphile")
        ok(f"login employee ({u_thabo['DisplayName']})")
    except Exception as e:
        fail("login employee", str(e))
        return 1

    try:
        lerato, u_lerato = client_for("nishen")
        ok(f"login manager ({u_lerato['DisplayName']})")
    except Exception as e:
        fail("login manager", str(e))
        return 1

    r = thabo.get("/api/admin/dashboard")
    if r.status_code == 403:
        ok("employee blocked from /api/admin/dashboard")
    else:
        fail("employee blocked from admin", f"expected 403 got {r.status_code}")

    r = lerato.get("/api/admin/dashboard")
    if r.status_code == 200:
        dash = r.json()
        ok(f"manager dashboard (pending={dash.get('PendingApprovals')}, active={dash.get('ActiveTrips')})")
    else:
        fail("manager dashboard", r.text)

    # --- Vehicles ---
    print("\n[2] Vehicles")
    r = thabo.get("/api/vehicles")
    if r.status_code != 200:
        fail("list vehicles", r.text)
        return 1
    vehicles = r.json()
    if len(vehicles) >= 2:
        ok(f"employee sees {len(vehicles)} active vehicles")
    else:
        fail("employee vehicles", f"expected >=2 got {len(vehicles)}")

    # Find Available vehicle (seed may have none free - free one first if needed)
    available = [v for v in vehicles if v["CurrentStatus"] == "Available"]
    print(f"     Available now: {len(available)}")

    # --- Seed state actions: Faiz check-in + Nishen key return to free Corolla ---
    print("\n[3] Clear seeded In Use trip (Faiz) to free a vehicle")
    sipho, _ = client_for("faiz")
    mine = sipho.get("/api/bookings/mine").json()
    checkout_booking = next(
        (b for b in mine if b["BookingStatus"] in ("Checked Out", "Flagged") and b.get("CheckOutTimestamp") and not b.get("CheckInTimestamp")),
        None,
    )
    if not checkout_booking:
        fail("find Faiz checked-out booking", "none found")
    else:
        bid = checkout_booking["BookingID"]
        mileage = (checkout_booking.get("CheckOutMileage") or 45200) + 10
        r = sipho.post(
            f"/api/bookings/{bid}/check-in",
            json={
                "Mileage": mileage,
                "LocationText": "GFS Basement Bay A1",
                "Latitude": -33.92,
                "Longitude": 18.42,
                "Photos": five_photos(),
                "DamageNoted": False,
            },
        )
        if r.status_code == 200:
            ok(f"Faiz check-in booking #{bid}")
        else:
            fail("Faiz check-in", r.text)

        r = lerato.post(f"/api/bookings/{bid}/key-returned")
        if r.status_code == 200 and r.json().get("BookingStatus") == "Closed":
            ok("Nishen confirms key return -> Closed")
        else:
            fail("key return", f"{r.status_code} {r.text}")

    # --- Request blocked when vehicle reserved/in use ---
    print("\n[4] Request validation")
    vehicles = thabo.get("/api/vehicles").json()
    reserved = next((v for v in vehicles if v["CurrentStatus"] != "Available"), None)
    if reserved:
        r = thabo.post(
            "/api/bookings",
            json={
                "VehicleID": reserved["VehicleID"],
                "BookingType": "Immediate",
                "PurposeReason": "Should fail",
                "Destination": "Nowhere",
            },
        )
        if r.status_code == 400:
            ok("cannot request non-Available vehicle")
        else:
            fail("request non-available", f"expected 400 got {r.status_code} {r.text}")

    available = [v for v in vehicles if v["CurrentStatus"] == "Available"]
    if not available:
        fail("need Available vehicle for happy path", "none free after Faiz return")
        print(f"\nResults: {PASS} passed, {FAIL} failed")
        return 1
    vehicle = available[0]
    ok(f"using Available vehicle {vehicle['RegistrationNumber']}")

    # --- Happy path ---
    print("\n[5] Happy path: request -> approve -> key -> check-out -> check-in -> key return")
    r = thabo.post(
        "/api/bookings",
        json={
            "VehicleID": vehicle["VehicleID"],
            "BookingType": "Immediate",
            "PurposeReason": "Demo site visit",
            "Destination": "Cape Town CBD",
        },
    )
    if r.status_code != 200:
        fail("create booking", r.text)
        return 1
    booking = r.json()
    bid = booking["BookingID"]
    ok(f"Omphile request -> Pending #{bid}")

    # Cancel test on a second request if possible later; first decide
    r = lerato.post(f"/api/bookings/{bid}/decide", json={"Decision": "Approve"})
    if r.status_code == 200 and r.json()["BookingStatus"] == "Approved":
        ok("Nishen approve")
    else:
        fail("approve", r.text)
        return 1

    # Check-out blocked without key
    r = thabo.post(
        f"/api/bookings/{bid}/check-out",
        json={
            "Mileage": vehicle["CurrentMileage"] + 1,
            "LocationText": "Bay A1",
            "Photos": five_photos(),
        },
    )
    if r.status_code == 400 and "key" in r.text.lower():
        ok("check-out blocked without KeyCollected")
    else:
        fail("check-out without key", f"{r.status_code} {r.text}")

    # Neo cannot hand over keys (not the approver)
    neo, _ = client_for("neo")
    r = neo.post(f"/api/bookings/{bid}/key-collected")
    if r.status_code == 403:
        ok("Neo (not approver) cannot confirm key handover")
    else:
        fail("wrong manager key handover", f"{r.status_code} {r.text}")

    r = lerato.post(f"/api/bookings/{bid}/key-collected")
    if r.status_code == 200 and r.json().get("KeyCollected") is True:
        ok("Nishen key handover")
        booking = r.json()
    else:
        fail("key collected", r.text)
        return 1

    out_mileage = vehicle["CurrentMileage"] + 5
    r = thabo.post(
        f"/api/bookings/{bid}/check-out",
        json={
            "Mileage": out_mileage,
            "LocationText": "GFS Basement Bay A1",
            "Latitude": -33.92,
            "Longitude": 18.42,
            "Photos": five_photos(),
        },
    )
    if r.status_code == 200 and r.json()["BookingStatus"] == "Checked Out":
        ok("Omphile check-out")
    else:
        fail("check-out", r.text)
        return 1

    # Mileage gate
    r = thabo.post(
        f"/api/bookings/{bid}/check-in",
        json={
            "Mileage": out_mileage - 1,
            "LocationText": "Bay A1",
            "Photos": five_photos(),
            "DamageNoted": False,
        },
    )
    if r.status_code == 400:
        ok("check-in rejects mileage < check-out")
    else:
        fail("mileage gate", f"{r.status_code} {r.text}")

    r = thabo.post(
        f"/api/bookings/{bid}/check-in",
        json={
            "Mileage": out_mileage + 20,
            "LocationText": "GFS Basement Bay A1",
            "Latitude": -33.92,
            "Longitude": 18.42,
            "Photos": five_photos(),
            "DamageNoted": True,
            "DamageDescription": "Small dent on front bumper",
        },
    )
    if r.status_code == 200 and r.json().get("DamageNoted") is True:
        ok("Omphile check-in with damage report")
    else:
        fail("check-in with damage", r.text)
        return 1

    # Incident created
    incidents = lerato.get("/api/admin/incidents").json()
    damage = [i for i in incidents if i["BookingID"] == bid and i["FlagType"] == "Damage"]
    if damage:
        ok(f"Damage incident auto-created (#{damage[0]['IncidentID']})")
    else:
        fail("damage incident", "not found")

    r = lerato.post(f"/api/bookings/{bid}/key-returned")
    if r.status_code == 200 and r.json()["BookingStatus"] == "Closed":
        ok("Nishen key return -> Closed")
    else:
        fail("final key return", r.text)

    # --- Cancel while pending ---
    print("\n[6] Cancel while Pending Approval only")
    vehicles = thabo.get("/api/vehicles").json()
    free = next((v for v in vehicles if v["CurrentStatus"] == "Available"), None)
    if free:
        r = thabo.post(
            "/api/bookings",
            json={
                "VehicleID": free["VehicleID"],
                "BookingType": "Immediate",
                "PurposeReason": "Will cancel",
                "Destination": "Test",
            },
        )
        cancel_id = r.json()["BookingID"]
        r = thabo.post(f"/api/bookings/{cancel_id}/cancel")
        if r.status_code == 200 and r.json()["BookingStatus"] == "Cancelled":
            ok("cancel pending booking")
        else:
            fail("cancel pending", r.text)
    else:
        print("     SKIP cancel test (no Available vehicle)")

    # --- Notifications & audit ---
    print("\n[7] Notifications & audit")
    notes = lerato.get("/api/admin/notifications").json()
    if len(notes) >= 1:
        ok(f"notifications log has {len(notes)} entries")
    else:
        fail("notifications", "empty")

    audit = lerato.get("/api/admin/audit").json()
    if len(audit) >= 1:
        ok(f"audit log has {len(audit)} entries")
    else:
        fail("audit", "empty")

    # Purpose required
    print("\n[8] Required fields")
    free = next((v for v in thabo.get("/api/vehicles").json() if v["CurrentStatus"] == "Available"), None)
    if free:
        r = thabo.post(
            "/api/bookings",
            json={
                "VehicleID": free["VehicleID"],
                "BookingType": "Immediate",
                "PurposeReason": " ",
                "Destination": "X",
            },
        )
        if r.status_code == 422:
            ok("blank PurposeReason rejected")
        else:
            fail("blank purpose", f"{r.status_code} {r.text}")
    else:
        print("     SKIP purpose validation (no Available vehicle)")

    print(f"\n=== Results: {PASS} passed, {FAIL} failed ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
