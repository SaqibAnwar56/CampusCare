"""Domain constants shared by models, services and templates."""

ROLE_REQUESTER = "requester"   # Student / Faculty
ROLE_STAFF = "staff"           # Maintenance staff
ROLE_ADMIN = "admin"           # Administrator
ROLES = (ROLE_REQUESTER, ROLE_STAFF, ROLE_ADMIN)
ROLE_LABELS = {ROLE_REQUESTER: "Student / Faculty", ROLE_STAFF: "Maintenance Staff", ROLE_ADMIN: "Administrator"}

STATUSES = ("Submitted", "Under Review", "Assigned", "In Progress", "Resolved", "Closed", "Rejected")
OPEN_STATUSES = ("Submitted", "Under Review", "Assigned", "In Progress")
WORKFLOW_STEPS = ("Submitted", "Under Review", "Assigned", "In Progress", "Resolved", "Closed")

PRIORITIES = ("Low", "Medium", "High", "Critical")
PRIORITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
# Target resolution time in hours (service-level target used to flag overdue requests)
SLA_HOURS = {"Critical": 8, "High": 24, "Medium": 72, "Low": 168}

CATEGORIES = (
    "Electrical", "Plumbing & Water", "HVAC / Cooling", "IT & Network",
    "Furniture & Fixtures", "Cleaning & Sanitation", "Safety & Security", "Other",
)
SAFETY_CATEGORY = "Safety & Security"
BUILDINGS = (
    "Main Academic Block", "Software Engineering Department", "Central Library",
    "Computer Lab Complex", "Administration Block", "Cafeteria", "Sports Complex", "Hostel Block",
)

# Words that indicate an immediate danger to people or property.
CRITICAL_KEYWORDS = (
    "fire", "smoke", "sparking", "sparks", "short circuit", "electric shock", "exposed wire",
    "gas leak", "flooding", "flooded", "collapse", "trapped",
)

EVENT_STATUS, EVENT_ASSIGNMENT, EVENT_PRIORITY = "status", "assignment", "priority"
