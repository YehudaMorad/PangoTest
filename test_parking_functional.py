import pytest
import requests
from bs4 import BeautifulSoup
from parking_app import ParkingApp

BASE_URL = 'http://127.0.0.1:5000'
DRIVER1_USERNAME = "DRIVER1"
DRIVER2_USERNAME = "DRIVER2"
DEFAULT_PASSWORD = "password"
CAR_PLATE_1 = "22224444"
CAR_PLATE_2 = "99998888"
SLOT_1 = "22"
ADMIN_USER = "admin"
ADMIN_PASS = "password"

def extract_flash_message(html):
    soup = BeautifulSoup(html, "html.parser")
    alert = soup.find(class_=["alert", "alert-danger", "alert-warning", "alert-info"])
    return alert.get_text(strip=True) if alert else ""

@pytest.fixture(scope="class", autouse=True)
def cleanup_sessions_before_and_after(app):
    """Close all open sessions before AND after the class."""
    session = requests.Session()
    app.login(session, ADMIN_USER, ADMIN_PASS)
   
    close_all_sessions(session, app)

    yield 

    close_all_sessions(session, app)
    session.close()

def close_all_sessions(session, app):
    dash = session.get(f"{BASE_URL}/").text
    soup = BeautifulSoup(dash, "html.parser")
    for tr in soup.find_all("tr"):
        form = tr.find("form", {"action": True})
        if form and "/end/" in form['action']:
            session_id = form['action'].split("/end/")[1]
            csrf_token = app.get_csrf_token(session, BASE_URL)
            session.post(f"{BASE_URL}/end/{session_id}", data={'csrf_token': csrf_token}, allow_redirects=True)
@pytest.fixture(scope="class")
def app():
    return ParkingApp(BASE_URL)

@pytest.fixture(scope="class")
def admin_session(app):
    s = requests.Session()
    app.login(s, "admin", DEFAULT_PASSWORD)
    return s

@pytest.fixture(scope="class")
def driver1(app, admin_session):
    if not app.user_exists(admin_session, DRIVER1_USERNAME):
        app.add_user(admin_session, DRIVER1_USERNAME, DEFAULT_PASSWORD)
    s = requests.Session()
    app.login(s, DRIVER1_USERNAME, DEFAULT_PASSWORD)
    return s

@pytest.fixture(scope="class")
def driver2(app, admin_session):
    if not app.user_exists(admin_session, DRIVER2_USERNAME):
        app.add_user(admin_session, DRIVER2_USERNAME, DEFAULT_PASSWORD)
    s = requests.Session()
    app.login(s, DRIVER2_USERNAME, DEFAULT_PASSWORD)
    return s

class TestParkingFunctional:

    def test_create_drivers(self, app, admin_session, request):
        request.node._report_sections.append(("call", "Step", "Creating DRIVER1 and DRIVER2 and verifying uniqueness"))
        app.add_user(admin_session, DRIVER1_USERNAME, DEFAULT_PASSWORD)
        app.add_user(admin_session, DRIVER2_USERNAME, DEFAULT_PASSWORD)
        users = admin_session.get(f"{BASE_URL}/users").text

        driver1_count = users.count(DRIVER1_USERNAME)
        driver2_count = users.count(DRIVER2_USERNAME)

        expected = 1
        actual = f"DRIVER1={driver1_count}, DRIVER2={driver2_count}"
        request.node._report_sections.append(("call", "Check", f"Expected each driver once. Actual: {actual}"))
        
        assert driver1_count == expected, f"Expected DRIVER1 count: {expected}, but got {driver1_count}"
        assert driver2_count == expected, f"Expected DRIVER2 count: {expected}, but got {driver2_count}"

    def test_duplicate_car_parking(self, app, driver1, driver2, request):
        request.node._report_sections.append(("call", "Step", f"DRIVER1 parks car {CAR_PLATE_1} in slot {SLOT_1}"))
        resp1 = app.start_parking(driver1, CAR_PLATE_1, SLOT_1)
        success_msg = extract_flash_message(resp1.text)

        request.node._report_sections.append(("call", "Check", f"Expected success message for DRIVER1. Got: '{success_msg}'"))
        assert "parking started" in success_msg.lower(), f"Expected success message, got: '{success_msg}'"

        request.node._report_sections.append(("call", "Step", f"DRIVER2 tries to park same car {CAR_PLATE_1} again in slot {SLOT_1}"))
        resp2 = app.start_parking(driver2, CAR_PLATE_1, SLOT_1)
        error_msg = extract_flash_message(resp2.text)

        request.node._report_sections.append(("call", "Check", f"Expected duplicate error. Got: '{error_msg}'"))
        assert "already parked" in error_msg.lower() or "duplicate" in error_msg.lower(), \
            f"Expected duplicate parking error, but got: '{error_msg}'"

    def test_duplicate_slot_parking(self, app, driver2, request):
        request.node._report_sections.append(("call", "Step", f"DRIVER2 tries to park car {CAR_PLATE_2} in already occupied slot {SLOT_1}"))
        resp = app.start_parking(driver2, CAR_PLATE_2, SLOT_1)
        error_msg = extract_flash_message(resp.text)

        request.node._report_sections.append(("call", "Check", f"Expected slot occupied error. Got: '{error_msg}'"))
        assert "slot is already occupied" in error_msg.lower(), \
            f"Expected slot occupied error, but got: '{error_msg}'"

    def test_close_and_verify_parking(self, app, admin_session, request):
        request.node._report_sections.append(("call", "Step", f"Closing session for car {CAR_PLATE_1} in slot {SLOT_1}"))
        dash = admin_session.get(f"{BASE_URL}/").text
        soup = BeautifulSoup(dash, "html.parser")

        session_id = None
        for tr in soup.find_all("tr"):
            if CAR_PLATE_1 in tr.text and SLOT_1 in tr.text:
                form = tr.find("form", {"action": True})
                if form and "/end/" in form['action']:
                    session_id = form['action'].split("/end/")[1]
                    break

        assert session_id is not None, "Session ID not found for closing"
        request.node._report_sections.append(("call", "Check", f"Found session_id={session_id}"))

        csrf_token = app.get_csrf_token(admin_session, BASE_URL)
        resp = admin_session.post(f"{BASE_URL}/end/{session_id}", data={'csrf_token': csrf_token}, allow_redirects=True)
        success_msg = extract_flash_message(resp.text)

        request.node._report_sections.append(("call", "Check", f"Expected session close success. Got: '{success_msg}'"))
        assert "parking ended" in success_msg.lower(), f"Expected parking ended message, but got '{success_msg}'"

        dash_after = admin_session.get(BASE_URL).text
        assert CAR_PLATE_1 not in dash_after, "Car still shown in open sessions after closing"
        request.node._report_sections.append(("call", "Check", f"Verified car {CAR_PLATE_1} not in open sessions"))

        history = admin_session.get(f"{BASE_URL}/history").text
        assert CAR_PLATE_1 in history, "Car not found in history after closing"
        request.node._report_sections.append(("call", "Check", f"Verified car {CAR_PLATE_1} found in parking history"))

