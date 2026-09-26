"""Demo data, loaded when the database is empty and ``AIRMATE_SEED`` is on.

OWNER: A2 (ml-demo) from here on. The lead's minimal version creates the demo cast and one device
so the app runs. A2 extends ``seed_if_empty`` with a week of realistic readings, puffs, symptoms and
risk history (use ``airmate_ml.simulate`` so it looks like the training data), community devices
around Atlanta for the hotspot map, and circle posts. Keep the ids below stable: the web app, the
device simulator and the demo script refer to them.
"""

from __future__ import annotations

from sqlalchemy import select

from ..db import Database
from ..models import Circle, Device, User

DEMO_USER_ID = "maya"  # the patient in the demo
DEMO_BUDDY_ID = "jordan"  # Maya's asthma buddy (gets the nudge on their phone)
DEMO_CAREGIVER_ID = "priya"  # Maya's mom
DEMO_DEVICE_ID = "airmate-01"
DEMO_CIRCLE_ID = "atl-asthma"

# Demo action plan in the usual green/yellow/red format. Airmate may only repeat doses written here
# (services/safety.py blocks anything else).
DEMO_ACTION_PLAN = {
    "controller": "Fluticasone 110 mcg inhaler, 2 puffs twice a day",
    "rescue": "Albuterol 90 mcg inhaler",
    "green": {"when": "Breathing is easy, no cough or wheeze, can do usual activities",
              "do": ["Take your controller: 2 puffs twice a day.", "Take 2 puffs of albuterol 15 minutes before exercise."]},
    "yellow": {"when": "Cough, wheeze, chest tightness, or waking at night",
               "do": ["Take 2 to 4 puffs of albuterol.", "Repeat every 20 minutes up to 3 times if needed.",
                      "Call Dr. Okafor's office if you need albuterol more than every 4 hours."]},
    "red": {"when": "Very short of breath, albuterol not helping, trouble walking or talking",
            "do": ["Take 4 to 6 puffs of albuterol now.", "Call 911 or go to the emergency room."]},
    "notes": "Demo action plan for a fictional patient.",
}


def seed_if_empty(db: Database) -> bool:
    with db.session() as session:
        if session.scalars(select(User.id).limit(1)).first() is not None:
            return False
        session.add(Circle(id=DEMO_CIRCLE_ID, name="Atlanta Asthma Circle",
                           description="People with asthma in Atlanta sharing tips and air alerts."))
        session.add_all([
            User(id=DEMO_USER_ID, name="Maya Johnson", age=19, lat=33.7766, lon=-84.3890, neighborhood="Midtown",
                 triggers=["dust", "odors"], action_plan=DEMO_ACTION_PLAN, buddy_id=DEMO_BUDDY_ID,
                 caregiver_ids=[DEMO_CAREGIVER_ID], circle_id=DEMO_CIRCLE_ID, doctor_name="Dr. Okafor",
                 emergency_contact={"name": "Priya Johnson", "relation": "mother"},
                 bio="Georgia Tech sophomore. Dust and cleaning sprays set me off."),
            User(id=DEMO_BUDDY_ID, name="Jordan Lee", age=20, lat=33.7812, lon=-84.3985, neighborhood="Home Park",
                 triggers=["pollen", "cold_air"], buddy_id=DEMO_USER_ID, circle_id=DEMO_CIRCLE_ID,
                 bio="Runner with exercise-induced asthma."),
            User(id=DEMO_CAREGIVER_ID, name="Priya Johnson", role="caregiver", cares_for_id=DEMO_USER_ID,
                 lat=33.7490, lon=-84.3880),
        ])
        session.add(Device(id=DEMO_DEVICE_ID, user_id=DEMO_USER_ID, label="Maya's bedroom",
                           lat=33.7766, lon=-84.3890))
        session.commit()
    return True
